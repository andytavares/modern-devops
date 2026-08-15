package main

import (
	"os"
	"testing"
)

func TestLoadConfigRequiresBrokers(t *testing.T) {
	os.Clearenv()
	if _, err := loadConfig(); err == nil {
		t.Fatal("expected an error when KAFKA_BROKERS is unset")
	}
}

func TestLoadConfigDefaults(t *testing.T) {
	os.Clearenv()
	t.Setenv("KAFKA_BROKERS", "a:9092,b:9092")
	t.Setenv("DDB_TABLE", "orders")

	cfg, err := loadConfig()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(cfg.brokers) != 2 {
		t.Fatalf("expected 2 brokers, got %d", len(cfg.brokers))
	}
	if cfg.topic != "orders" {
		t.Fatalf("expected default topic 'orders', got %q", cfg.topic)
	}
	if cfg.group != "order-worker" {
		t.Fatalf("expected default group 'order-worker', got %q", cfg.group)
	}
}
