// Command order-worker consumes order events from Kafka and persists them to DynamoDB.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/dynamodb"
	ddbtypes "github.com/aws/aws-sdk-go-v2/service/dynamodb/types"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/twmb/franz-go/pkg/kgo"
)

var (
	processed = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "orders_processed_total",
		Help: "Order events consumed from Kafka and written to DynamoDB.",
	}, []string{"result"})

	processDuration = promauto.NewHistogram(prometheus.HistogramOpts{
		Name:    "order_process_duration_seconds",
		Help:    "Time to persist one order event.",
		Buckets: prometheus.DefBuckets,
	})

	lag = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "order_event_age_seconds",
		Help: "Age of the most recently processed event, from created_at to write time.",
	})
)

type orderEvent struct {
	OrderID     string `json:"order_id"`
	Customer    string `json:"customer"`
	SKU         string `json:"sku"`
	Quantity    int    `json:"quantity"`
	AmountCents int    `json:"amount_cents"`
	CreatedAt   string `json:"created_at"`
	S3Key       string `json:"s3_key"`
	Signature   string `json:"signature"`
}

type config struct {
	brokers []string
	topic   string
	group   string
	table   string
	region  string
	version string
	addr    string
}

func loadConfig() (config, error) {
	c := config{
		topic:   getenv("KAFKA_TOPIC", "orders"),
		group:   getenv("KAFKA_GROUP", "order-worker"),
		region:  getenv("AWS_DEFAULT_REGION", "us-east-1"),
		version: getenv("SERVICE_VERSION", "dev"),
		addr:    getenv("METRICS_ADDR", ":9090"),
	}
	brokers := os.Getenv("KAFKA_BROKERS")
	if brokers == "" {
		return c, errors.New("required environment variable KAFKA_BROKERS is not set")
	}
	c.brokers = strings.Split(brokers, ",")
	c.table = os.Getenv("DDB_TABLE")
	if c.table == "" {
		return c, errors.New("required environment variable DDB_TABLE is not set")
	}
	return c, nil
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	cfg, err := loadConfig()
	if err != nil {
		slog.Error("configuration error", "err", err)
		os.Exit(1)
	}

	// SIGTERM is what Kubernetes sends first on pod deletion. Handling it is the
	// difference between a graceful rolling update and dropped in-flight work.
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// AWS_ENDPOINT_URL is honoured natively by aws-sdk-go-v2, so pointing at Floci
	// needs no code change at all — the same binary runs against real AWS.
	awsCfg, err := awsconfig.LoadDefaultConfig(ctx, awsconfig.WithRegion(cfg.region))
	if err != nil {
		slog.Error("failed to load aws config", "err", err)
		os.Exit(1)
	}
	ddb := dynamodb.NewFromConfig(awsCfg)

	client, err := kgo.NewClient(
		kgo.SeedBrokers(cfg.brokers...),
		kgo.ConsumerGroup(cfg.group),
		kgo.ConsumeTopics(cfg.topic),
		kgo.ConsumeResetOffset(kgo.NewOffset().AtStart()),
		kgo.DisableAutoCommit(), // we commit only after a successful DynamoDB write
		kgo.SessionTimeout(30*time.Second),
	)
	if err != nil {
		slog.Error("failed to create kafka client", "err", err)
		os.Exit(1)
	}
	defer client.Close()

	ready := &atomicBool{}
	go serveHTTP(ctx, cfg, ready)

	if err := client.Ping(ctx); err != nil {
		slog.Error("kafka not reachable", "err", err)
		os.Exit(1)
	}
	ready.set(true)
	slog.Info("order-worker started", "version", cfg.version, "topic", cfg.topic, "table", cfg.table)

	for {
		fetches := client.PollFetches(ctx)
		if ctx.Err() != nil {
			slog.Info("shutting down")
			return
		}
		if errs := fetches.Errors(); len(errs) > 0 {
			for _, e := range errs {
				slog.Error("fetch error", "topic", e.Topic, "partition", e.Partition, "err", e.Err)
			}
			continue
		}

		fetches.EachRecord(func(r *kgo.Record) {
			if err := handle(ctx, ddb, cfg.table, r); err != nil {
				processed.WithLabelValues("error").Inc()
				slog.Error("failed to process record", "offset", r.Offset, "err", err)
				return
			}
			processed.WithLabelValues("ok").Inc()
		})

		// Commit after the batch. At-least-once delivery: a crash between the
		// DynamoDB write and this commit replays the record. PutItem on the same
		// order_id is idempotent, so replay is harmless. That is the trade we
		// chose — see the note below.
		if err := client.CommitUncommittedOffsets(ctx); err != nil {
			slog.Error("commit failed", "err", err)
		}
	}
}

func handle(ctx context.Context, ddb *dynamodb.Client, table string, r *kgo.Record) error {
	start := time.Now()
	defer func() { processDuration.Observe(time.Since(start).Seconds()) }()

	var ev orderEvent
	if err := json.Unmarshal(r.Value, &ev); err != nil {
		// A malformed message will never become valid. Skipping it (rather than
		// retrying forever) keeps the partition moving. In production this record
		// goes to a dead-letter topic instead of the floor.
		slog.Warn("skipping malformed record", "offset", r.Offset, "err", err)
		return nil
	}

	if ts, err := time.Parse(time.RFC3339, ev.CreatedAt); err == nil {
		lag.Set(time.Since(ts).Seconds())
	}

	writeCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	_, err := ddb.PutItem(writeCtx, &dynamodb.PutItemInput{
		TableName: aws.String(table),
		Item: map[string]ddbtypes.AttributeValue{
			"order_id":     &ddbtypes.AttributeValueMemberS{Value: ev.OrderID},
			"customer":     &ddbtypes.AttributeValueMemberS{Value: ev.Customer},
			"sku":          &ddbtypes.AttributeValueMemberS{Value: ev.SKU},
			"quantity":     &ddbtypes.AttributeValueMemberN{Value: strconv.Itoa(ev.Quantity)},
			"amount_cents": &ddbtypes.AttributeValueMemberN{Value: strconv.Itoa(ev.AmountCents)},
			"created_at":   &ddbtypes.AttributeValueMemberS{Value: ev.CreatedAt},
			"s3_key":       &ddbtypes.AttributeValueMemberS{Value: ev.S3Key},
			"signature":    &ddbtypes.AttributeValueMemberS{Value: ev.Signature},
		},
	})
	if err != nil {
		return err
	}
	slog.Info("persisted order", "order_id", ev.OrderID, "offset", r.Offset)
	return nil
}

func serveHTTP(ctx context.Context, cfg config, ready *atomicBool) {
	mux := http.NewServeMux()
	mux.Handle("/metrics", promhttp.Handler())
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, _ *http.Request) {
		if !ready.get() {
			w.WriteHeader(http.StatusServiceUnavailable)
			_, _ = w.Write([]byte(`{"status":"not-ready"}`))
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ready"}`))
	})

	srv := &http.Server{Addr: cfg.addr, Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	go func() {
		<-ctx.Done()
		shutCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = srv.Shutdown(shutCtx)
	}()
	if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		slog.Error("metrics server failed", "err", err)
	}
}
