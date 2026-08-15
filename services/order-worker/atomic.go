package main

import "sync/atomic"

type atomicBool struct{ v atomic.Bool }

func (a *atomicBool) set(b bool) { a.v.Store(b) }
func (a *atomicBool) get() bool  { return a.v.Load() }
