package atpsdk

import (
	"context"
	"fmt"
	"sync"
	"testing"
	"time"
)

func TestNewATPClient(t *testing.T) {
	config := SDKConfig{
		BaseURL:  "http://localhost:8000",
		WSURL:    "ws://localhost:8000",
		APIKey:   "test-key",
		TenantID: "test-tenant",
	}

	client := NewATPClient(config)

	if client == nil {
		t.Fatal("NewATPClient returned nil")
	}

	if client.config.TenantID != "test-tenant" {
		t.Errorf("Expected tenant ID 'test-tenant', got '%s'", client.config.TenantID)
	}

	if client.config.SessionID == "" {
		t.Error("Session ID should not be empty")
	}
}

func TestFrameBuilder(t *testing.T) {
	fb := NewFrameBuilder("test-session", "test-tenant")

	request := CompletionRequest{
		Prompt:      "Test prompt",
		MaxTokens:   100,
		Temperature: 0.7,
	}

	frame := fb.BuildCompletionFrame("test-stream", request)

	if frame.Type != "completion_request" {
		t.Errorf("Expected frame type 'completion_request', got '%s'", frame.Type)
	}

	if frame.StreamID != "test-stream" {
		t.Errorf("Expected stream ID 'test-stream', got '%s'", frame.StreamID)
	}

	if frame.MsgSeq != 1 {
		t.Errorf("Expected message sequence 1, got %d", frame.MsgSeq)
	}

	if frame.Meta.EnvironmentID != "test-tenant" {
		t.Errorf("Expected environment ID 'test-tenant', got '%s'", frame.Meta.EnvironmentID)
	}
}

func TestFrameSerialization(t *testing.T) {
	fb := NewFrameBuilder("test-session", "test-tenant")

	request := CompletionRequest{
		Prompt:    "Test prompt",
		MaxTokens: 50,
	}

	frame := fb.BuildCompletionFrame("test-stream", request)

	// Serialize
	data, err := fb.SerializeFrame(frame)
	if err != nil {
		t.Fatalf("Failed to serialize frame: %v", err)
	}

	// Deserialize
	deserializedFrame, err := fb.DeserializeFrame(data)
	if err != nil {
		t.Fatalf("Failed to deserialize frame: %v", err)
	}

	// Compare
	if deserializedFrame.Type != frame.Type {
		t.Errorf("Type mismatch: expected %s, got %s", frame.Type, deserializedFrame.Type)
	}

	if deserializedFrame.StreamID != frame.StreamID {
		t.Errorf("StreamID mismatch: expected %s, got %s", frame.StreamID, deserializedFrame.StreamID)
	}
}

func TestConcurrentRequests(t *testing.T) {
	// This test simulates concurrent usage of the ATP client
	// Note: This would normally connect to a real ATP Router, but for testing
	// we'll just test the client structure and concurrency safety

	config := SDKConfig{
		BaseURL:  "http://localhost:8000",
		WSURL:    "ws://localhost:8000",
		TenantID: "test-tenant",
	}

	client := NewATPClient(config)

	var wg sync.WaitGroup
	numGoroutines := 10
	numRequestsPerGoroutine := 5

	// Test concurrent client creation and configuration access
	for i := 0; i < numGoroutines; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()

			// Test concurrent access to client methods
			for j := 0; j < numRequestsPerGoroutine; j++ {
				// Test IsConnected() concurrency
				_ = client.IsConnected()

				// Test frame builder creation (simulating request preparation)
				fb := NewFrameBuilder(client.config.SessionID, client.config.TenantID)
				request := CompletionRequest{
					Prompt:    "Concurrent test prompt",
					MaxTokens: 10,
				}
				_ = fb.BuildCompletionFrame("test-stream", request)
			}
		}(i)
	}

	// Wait for all goroutines to complete
	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		// All goroutines completed successfully
	case <-time.After(10 * time.Second):
		t.Fatal("Concurrent test timed out")
	}
}

func TestHeartbeatFrame(t *testing.T) {
	fb := NewFrameBuilder("test-session", "test-tenant")

	frame := fb.BuildHeartbeatFrame()

	if frame.Type != "heartbeat" {
		t.Errorf("Expected frame type 'heartbeat', got '%s'", frame.Type)
	}

	if frame.Timestamp == 0 {
		t.Error("Heartbeat frame should have a timestamp")
	}
}

func TestCompletionRequestParsing(t *testing.T) {
	fb := NewFrameBuilder("test-session", "test-tenant")

	request := CompletionRequest{
		Prompt:      "Test completion",
		MaxTokens:   200,
		Temperature: 0.8,
		TopP:        0.9,
		Stop:        []string{"\n", "END"},
	}

	frame := fb.BuildCompletionFrame("test-stream", request)

	// Check payload contents
	payload := frame.Payload

	if prompt, ok := payload["prompt"].(string); !ok || prompt != "Test completion" {
		t.Errorf("Expected prompt 'Test completion', got '%v'", payload["prompt"])
	}

	if maxTokens, ok := payload["max_tokens"].(int); !ok || maxTokens != 200 {
		t.Errorf("Expected max_tokens 200, got '%v'", payload["max_tokens"])
	}

	if temperature, ok := payload["temperature"].(float64); !ok || temperature != 0.8 {
		t.Errorf("Expected temperature 0.8, got '%v'", payload["temperature"])
	}
}

func BenchmarkFrameBuilding(b *testing.B) {
	fb := NewFrameBuilder("bench-session", "bench-tenant")
	request := CompletionRequest{
		Prompt:    "Benchmark prompt",
		MaxTokens: 100,
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		streamID := fmt.Sprintf("stream-%d", i)
		_ = fb.BuildCompletionFrame(streamID, request)
	}
}

func BenchmarkFrameSerialization(b *testing.B) {
	fb := NewFrameBuilder("bench-session", "bench-tenant")
	request := CompletionRequest{
		Prompt:    "Benchmark prompt",
		MaxTokens: 100,
	}
	frame := fb.BuildCompletionFrame("bench-stream", request)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, _ = fb.SerializeFrame(frame)
	}
}

func TestCapabilityAdvertisement(t *testing.T) {
	capability := CapabilityAdvertisement{
		AdapterID:          "test-adapter-1",
		AdapterType:        "ollama",
		Capabilities:       []string{"text-generation", "embedding"},
		Models:             []string{"llama2:7b", "codellama:13b"},
		MaxTokens:          intPtr(4096),
		SupportedLanguages: []string{"en", "es"},
		CostPerTokenMicros: intPtr(100),
		HealthEndpoint:     stringPtr("http://localhost:8080/health"),
		Version:            stringPtr("1.0.0"),
		Metadata: map[string]interface{}{
			"region": "us-west-2",
		},
	}

	if capability.AdapterID != "test-adapter-1" {
		t.Errorf("Expected adapter ID 'test-adapter-1', got '%s'", capability.AdapterID)
	}

	if capability.AdapterType != "ollama" {
		t.Errorf("Expected adapter type 'ollama', got '%s'", capability.AdapterType)
	}

	if len(capability.Capabilities) != 2 {
		t.Errorf("Expected 2 capabilities, got %d", len(capability.Capabilities))
	}

	if capability.Capabilities[0] != "text-generation" {
		t.Errorf("Expected first capability 'text-generation', got '%s'", capability.Capabilities[0])
	}
}

func TestBuildCapabilityFrame(t *testing.T) {
	fb := NewFrameBuilder("test-session", "test-tenant")

	capability := CapabilityAdvertisement{
		AdapterID:    "test-adapter-1",
		AdapterType:  "ollama",
		Capabilities: []string{"text-generation"},
		Models:       []string{"llama2:7b"},
	}

	frame := fb.BuildCapabilityFrame("capability-stream", capability)

	if frame.Type != "adapter.capability" {
		t.Errorf("Expected frame type 'adapter.capability', got '%s'", frame.Type)
	}

	if frame.StreamID != "capability-stream" {
		t.Errorf("Expected stream ID 'capability-stream', got '%s'", frame.StreamID)
	}

	if frame.MsgSeq != 1 {
		t.Errorf("Expected message sequence 1, got %d", frame.MsgSeq)
	}

	if len(frame.Flags) == 0 || frame.Flags[0] != "capability" {
		t.Errorf("Expected capability flag, got %v", frame.Flags)
	}

	if frame.QoS != "bronze" {
		t.Errorf("Expected QoS 'bronze', got '%s'", frame.QoS)
	}

	if frame.TTL != 30 {
		t.Errorf("Expected TTL 30, got %d", frame.TTL)
	}

	// Check payload contents
	payload := frame.Payload

	if adapterID, ok := payload["adapter_id"].(string); !ok || adapterID != "test-adapter-1" {
		t.Errorf("Expected adapter_id 'test-adapter-1', got '%v'", payload["adapter_id"])
	}

	if adapterType, ok := payload["adapter_type"].(string); !ok || adapterType != "ollama" {
		t.Errorf("Expected adapter_type 'ollama', got '%v'", payload["adapter_type"])
	}

	if capabilities, ok := payload["capabilities"].([]string); !ok || len(capabilities) != 1 || capabilities[0] != "text-generation" {
		t.Errorf("Expected capabilities ['text-generation'], got '%v'", payload["capabilities"])
	}
}

func TestCapabilityFrameSerialization(t *testing.T) {
	fb := NewFrameBuilder("test-session", "test-tenant")

	capability := CapabilityAdvertisement{
		AdapterID:    "test-adapter-1",
		AdapterType:  "ollama",
		Capabilities: []string{"text-generation", "embedding"},
		Models:       []string{"llama2:7b"},
		Version:      stringPtr("1.0.0"),
	}

	frame := fb.BuildCapabilityFrame("capability-stream", capability)

	// Serialize
	data, err := fb.SerializeFrame(frame)
	if err != nil {
		t.Fatalf("Failed to serialize capability frame: %v", err)
	}

	// Deserialize
	deserializedFrame, err := fb.DeserializeFrame(data)
	if err != nil {
		t.Fatalf("Failed to deserialize capability frame: %v", err)
	}

	// Compare key fields
	if deserializedFrame.Type != "adapter.capability" {
		t.Errorf("Type mismatch: expected 'adapter.capability', got '%s'", deserializedFrame.Type)
	}

	if deserializedFrame.StreamID != "capability-stream" {
		t.Errorf("StreamID mismatch: expected 'capability-stream', got '%s'", deserializedFrame.StreamID)
	}

	// Check payload was preserved
	payload := deserializedFrame.Payload
	if adapterID, ok := payload["adapter_id"].(string); !ok || adapterID != "test-adapter-1" {
		t.Errorf("Adapter ID not preserved in serialization: got '%v'", payload["adapter_id"])
	}

	if adapterType, ok := payload["adapter_type"].(string); !ok || adapterType != "ollama" {
		t.Errorf("Adapter type not preserved in serialization: got '%v'", payload["adapter_type"])
	}

	if capabilities, ok := payload["capabilities"].([]interface{}); !ok || len(capabilities) != 2 {
		t.Errorf("Capabilities not preserved in serialization: got '%v'", payload["capabilities"])
	}
}

func TestAdvertiseCapabilitiesClient(t *testing.T) {
	config := SDKConfig{
		BaseURL:  "http://localhost:8000",
		WSURL:    "ws://localhost:8000",
		TenantID: "test-tenant",
	}

	client := NewATPClient(config)

	capability := CapabilityAdvertisement{
		AdapterID:    "test-adapter-1",
		AdapterType:  "ollama",
		Capabilities: []string{"text-generation"},
		Models:       []string{"llama2:7b"},
	}

	// Test that AdvertiseCapabilities doesn't panic when not connected
	// (In a real scenario, this would attempt to connect)
	defer func() {
		if r := recover(); r != nil {
			t.Errorf("AdvertiseCapabilities panicked: %v", r)
		}
	}()

	// Note: We can't easily test the full AdvertiseCapabilities flow without
	// a mock WebSocket server, but we can test that the method exists and
	// the frame building works correctly
	ctx := context.Background()

	// This will fail to connect, but shouldn't panic
	err := client.AdvertiseCapabilities(ctx, capability)
	// We expect an error since there's no server running
	if err == nil {
		t.Log("AdvertiseCapabilities completed without error (unexpected in test environment)")
	}
}

func TestConcurrentCapabilityAdvertisement(t *testing.T) {
	config := SDKConfig{
		BaseURL:  "http://localhost:8000",
		WSURL:    "ws://localhost:8000",
		TenantID: "test-tenant",
	}

	client := NewATPClient(config)

	var wg sync.WaitGroup
	numGoroutines := 5

	// Test concurrent capability advertisement preparation
	for i := 0; i < numGoroutines; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()

			capability := CapabilityAdvertisement{
				AdapterID:    fmt.Sprintf("adapter-%d", id),
				AdapterType:  "ollama",
				Capabilities: []string{"text-generation"},
				Models:       []string{"llama2:7b"},
			}

			// Test frame building concurrency
			fb := NewFrameBuilder(client.config.SessionID, client.config.TenantID)
			streamID := fmt.Sprintf("capability-stream-%d", id)
			frame := fb.BuildCapabilityFrame(streamID, capability)

			if frame.Type != "adapter.capability" {
				t.Errorf("Concurrent frame building failed: expected type 'adapter.capability', got '%s'", frame.Type)
			}

			if frame.Payload["adapter_id"] != fmt.Sprintf("adapter-%d", id) {
				t.Errorf("Concurrent frame building failed: adapter ID mismatch")
			}
		}(i)
	}

	// Wait for all goroutines to complete
	done := make(chan struct{})
	go func() {
		wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		// All goroutines completed successfully
	case <-time.After(5 * time.Second):
		t.Fatal("Concurrent capability advertisement test timed out")
	}
}

func BenchmarkCapabilityFrameBuilding(b *testing.B) {
	fb := NewFrameBuilder("bench-session", "bench-tenant")

	capability := CapabilityAdvertisement{
		AdapterID:    "bench-adapter",
		AdapterType:  "ollama",
		Capabilities: []string{"text-generation", "embedding"},
		Models:       []string{"llama2:7b", "codellama:13b"},
		MaxTokens:    intPtr(4096),
		Version:      stringPtr("1.0.0"),
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		streamID := fmt.Sprintf("capability-stream-%d", i)
		_ = fb.BuildCapabilityFrame(streamID, capability)
	}
}

func BenchmarkCapabilityFrameSerialization(b *testing.B) {
	fb := NewFrameBuilder("bench-session", "bench-tenant")

	capability := CapabilityAdvertisement{
		AdapterID:    "bench-adapter",
		AdapterType:  "ollama",
		Capabilities: []string{"text-generation"},
		Models:       []string{"llama2:7b"},
	}

	frame := fb.BuildCapabilityFrame("bench-stream", capability)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, _ = fb.SerializeFrame(frame)
	}
}

func TestHealthStatus(t *testing.T) {
	health := HealthStatus{
		AdapterID:        "test-adapter-1",
		Status:           "healthy",
		P95LatencyMS:     floatPtr(150.5),
		P50LatencyMS:     floatPtr(95.2),
		ErrorRate:        floatPtr(0.02),
		RequestsPerSecond: floatPtr(10.5),
		QueueDepth:       intPtr(3),
		MemoryUsageMB:    floatPtr(512.8),
		CPUUsagePercent:  floatPtr(45.2),
		UptimeSeconds:    intPtr(3600),
		Version:          stringPtr("1.0.0"),
		Metadata: map[string]interface{}{
			"region": "us-west-2",
		},
	}

	if health.AdapterID != "test-adapter-1" {
		t.Errorf("Expected adapter ID 'test-adapter-1', got '%s'", health.AdapterID)
	}

	if health.Status != "healthy" {
		t.Errorf("Expected status 'healthy', got '%s'", health.Status)
	}

	if *health.P95LatencyMS != 150.5 {
		t.Errorf("Expected p95 latency 150.5, got '%v'", health.P95LatencyMS)
	}
}

func TestBuildHealthFrame(t *testing.T) {
	fb := NewFrameBuilder("test-session", "test-tenant")

	health := HealthStatus{
		AdapterID:    "test-adapter-1",
		Status:       "healthy",
		P95LatencyMS: floatPtr(200.5),
		ErrorRate:    floatPtr(0.03),
	}

	frame := fb.BuildHealthFrame("health-stream", health)

	if frame.Type != "adapter.health" {
		t.Errorf("Expected frame type 'adapter.health', got '%s'", frame.Type)
	}

	if frame.StreamID != "health-stream" {
		t.Errorf("Expected stream ID 'health-stream', got '%s'", frame.StreamID)
	}

	if frame.MsgSeq != 1 {
		t.Errorf("Expected message sequence 1, got %d", frame.MsgSeq)
	}

	if len(frame.Flags) == 0 || frame.Flags[0] != "health" {
		t.Errorf("Expected health flag, got %v", frame.Flags)
	}

	if frame.QoS != "bronze" {
		t.Errorf("Expected QoS 'bronze', got '%s'", frame.QoS)
	}

	if frame.TTL != 60 {
		t.Errorf("Expected TTL 60, got %d", frame.TTL)
	}

	// Check payload contents
	payload := frame.Payload

	if adapterID, ok := payload["adapter_id"].(string); !ok || adapterID != "test-adapter-1" {
		t.Errorf("Expected adapter_id 'test-adapter-1', got '%v'", payload["adapter_id"])
	}

	if status, ok := payload["status"].(string); !ok || status != "healthy" {
		t.Errorf("Expected status 'healthy', got '%v'", payload["status"])
	}

	if p95Latency, ok := payload["p95_latency_ms"].(*float64); !ok || *p95Latency != 200.5 {
		t.Errorf("Expected p95_latency_ms 200.5, got '%v'", payload["p95_latency_ms"])
	}
}

func TestHealthFrameSerialization(t *testing.T) {
	fb := NewFrameBuilder("test-session", "test-tenant")

	health := HealthStatus{
		AdapterID:    "test-adapter-1",
		Status:       "degraded",
		P95LatencyMS: floatPtr(300.0),
		ErrorRate:    floatPtr(0.1),
		Version:      stringPtr("2.0.0"),
	}

	frame := fb.BuildHealthFrame("health-stream", health)

	// Serialize
	data, err := fb.SerializeFrame(frame)
	if err != nil {
		t.Fatalf("Failed to serialize health frame: %v", err)
	}

	// Deserialize
	deserializedFrame, err := fb.DeserializeFrame(data)
	if err != nil {
		t.Fatalf("Failed to deserialize health frame: %v", err)
	}

	// Compare key fields
	if deserializedFrame.Type != "adapter.health" {
		t.Errorf("Type mismatch: expected 'adapter.health', got '%s'", deserializedFrame.Type)
	}

	if deserializedFrame.StreamID != "health-stream" {
		t.Errorf("StreamID mismatch: expected 'health-stream', got '%s'", deserializedFrame.StreamID)
	}

	// Check payload was preserved
	payload := deserializedFrame.Payload
	if adapterID, ok := payload["adapter_id"].(string); !ok || adapterID != "test-adapter-1" {
		t.Errorf("Adapter ID not preserved in serialization: got '%v'", payload["adapter_id"])
	}

	if status, ok := payload["status"].(string); !ok || status != "degraded" {
		t.Errorf("Status not preserved in serialization: got '%v'", payload["status"])
	}
}

func TestReportHealthClient(t *testing.T) {
	config := SDKConfig{
		BaseURL:  "http://localhost:8000",
		WSURL:    "ws://localhost:8000",
		TenantID: "test-tenant",
	}

	client := NewATPClient(config)

	health := HealthStatus{
		AdapterID:    "test-adapter-1",
		Status:       "healthy",
		P95LatencyMS: floatPtr(150.0),
		ErrorRate:    floatPtr(0.01),
	}

	// Test that ReportHealth doesn't panic when not connected
	// (In a real scenario, this would attempt to connect)
	defer func() {
		if r := recover(); r != nil {
			t.Errorf("ReportHealth panicked: %v", r)
		}
	}()

	// Note: We can't easily test the full ReportHealth flow without
	// a mock WebSocket server, but we can test that the method exists and
	// the frame building works correctly
	ctx := context.Background()

	// This will fail to connect, but shouldn't panic
	err := client.ReportHealth(ctx, health)
	// We expect an error since there's no server running
	if err == nil {
		t.Log("ReportHealth completed without error (unexpected in test environment)")
	}
}

func BenchmarkHealthFrameBuilding(b *testing.B) {
	fb := NewFrameBuilder("bench-session", "bench-tenant")

	health := HealthStatus{
		AdapterID:        "bench-adapter",
		Status:           "healthy",
		P95LatencyMS:     floatPtr(100.0),
		P50LatencyMS:     floatPtr(50.0),
		ErrorRate:        floatPtr(0.02),
		RequestsPerSecond: floatPtr(20.0),
		MemoryUsageMB:    floatPtr(1024.0),
		CPUUsagePercent:  floatPtr(60.0),
		Version:          stringPtr("1.0.0"),
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		streamID := fmt.Sprintf("health-stream-%d", i)
		_ = fb.BuildHealthFrame(streamID, health)
	}
}

func BenchmarkHealthFrameSerialization(b *testing.B) {
	fb := NewFrameBuilder("bench-session", "bench-tenant")

	health := HealthStatus{
		AdapterID:    "bench-adapter",
		Status:       "healthy",
		P95LatencyMS: floatPtr(100.0),
		ErrorRate:    floatPtr(0.02),
	}

	frame := fb.BuildHealthFrame("bench-stream", health)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, _ = fb.SerializeFrame(frame)
	}
}

// Helper functions for creating pointers to primitive types
func intPtr(i int) *int {
	return &i
}

func floatPtr(f float64) *float64 {
	return &f
}

func stringPtr(s string) *string {
	return &s
}
