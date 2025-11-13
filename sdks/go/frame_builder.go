package atpsdk

import (
	"encoding/json"
	"fmt"
	"time"
)

// FrameBuilder handles construction of ATP protocol frames
type FrameBuilder struct {
	sessionID string
	tenantID  string
	msgSeqCounters map[string]int
}

// NewFrameBuilder creates a new frame builder
func NewFrameBuilder(sessionID, tenantID string) *FrameBuilder {
	return &FrameBuilder{
		sessionID:      sessionID,
		tenantID:       tenantID,
		msgSeqCounters: make(map[string]int),
	}
}

// getNextMsgSeq returns the next message sequence number for a stream
func (fb *FrameBuilder) getNextMsgSeq(streamID string) int {
	key := fmt.Sprintf("%s:%s", fb.sessionID, streamID)
	fb.msgSeqCounters[key]++
	return fb.msgSeqCounters[key]
}

// BuildCompletionFrame builds a completion request frame
func (fb *FrameBuilder) BuildCompletionFrame(streamID string, request CompletionRequest) Frame {
	msgSeq := fb.getNextMsgSeq(streamID)

	return Frame{
		Type:      "completion_request",
		Timestamp: time.Now().UnixMilli(),
		StreamID:  streamID,
		MsgSeq:    msgSeq,
		FragSeq:   0,
		Flags:     []string{},
		QoS:       "gold",
		TTL:       8,
		Window: Window{
			MaxParallel: 4,
			MaxTokens:   50000,
			MaxUSD:      1000000,
		},
		Meta: Meta{
			TaskType:      "completion",
			EnvironmentID: fb.tenantID,
		},
		Payload: map[string]interface{}{
			"prompt":      request.Prompt,
			"max_tokens":  request.MaxTokens,
			"temperature": request.Temperature,
			"top_p":       request.TopP,
			"stop":        request.Stop,
		},
	}
}

// BuildHeartbeatFrame builds a heartbeat frame
func (fb *FrameBuilder) BuildHeartbeatFrame() Frame {
	return Frame{
		Type:      "heartbeat",
		Timestamp: time.Now().UnixMilli(),
		Payload:   map[string]interface{}{},
	}
}

// BuildCapabilityFrame builds a capability advertisement frame
func (fb *FrameBuilder) BuildCapabilityFrame(streamID string, capability CapabilityAdvertisement) Frame {
	msgSeq := fb.getNextMsgSeq(streamID)

	return Frame{
		Type:      "adapter.capability",
		Timestamp: time.Now().UnixMilli(),
		StreamID:  streamID,
		MsgSeq:    msgSeq,
		FragSeq:   0,
		Flags:     []string{"capability"},
		QoS:       "bronze",
		TTL:       30, // Longer TTL for capability frames
		Window: Window{
			MaxParallel: 1,
			MaxTokens:   1000,
			MaxUSD:      10000,
		},
		Meta: Meta{
			EnvironmentID: fb.tenantID,
		},
		Payload: map[string]interface{}{
			"type":                 "adapter.capability",
			"adapter_id":           capability.AdapterID,
			"adapter_type":         capability.AdapterType,
			"capabilities":         capability.Capabilities,
			"models":               capability.Models,
			"max_tokens":           capability.MaxTokens,
			"supported_languages":  capability.SupportedLanguages,
			"cost_per_token_micros": capability.CostPerTokenMicros,
			"health_endpoint":      capability.HealthEndpoint,
			"version":              capability.Version,
			"metadata":             capability.Metadata,
		},
	}
}

// BuildHealthFrame builds a health status frame
func (fb *FrameBuilder) BuildHealthFrame(streamID string, health HealthStatus) Frame {
	msgSeq := fb.getNextMsgSeq(streamID)

	return Frame{
		Type:      "adapter.health",
		Timestamp: time.Now().UnixMilli(),
		StreamID:  streamID,
		MsgSeq:    msgSeq,
		FragSeq:   0,
		Flags:     []string{"health"},
		QoS:       "bronze",
		TTL:       60, // Health frames have longer TTL
		Window: Window{
			MaxParallel: 1,
			MaxTokens:   1000,
			MaxUSD:      10000,
		},
		Meta: Meta{},
		Payload: map[string]interface{}{
			"type":                 "adapter.health",
			"adapter_id":           health.AdapterID,
			"status":               health.Status,
			"p95_latency_ms":       health.P95LatencyMS,
			"p50_latency_ms":       health.P50LatencyMS,
			"p99_latency_ms":       health.P99LatencyMS,
			"requests_per_second":  health.RequestsPerSecond,
			"error_rate":           health.ErrorRate,
			"queue_depth":          health.QueueDepth,
			"memory_usage_mb":      health.MemoryUsageMB,
			"cpu_usage_percent":    health.CPUUsagePercent,
			"uptime_seconds":       health.UptimeSeconds,
			"version":              health.Version,
			"last_health_check":    time.Now().Unix(),
			"metadata":             health.Metadata,
		},
	}
}

// SerializeFrame serializes a frame to JSON bytes
func (fb *FrameBuilder) SerializeFrame(frame Frame) ([]byte, error) {
	return json.Marshal(frame)
}

// DeserializeFrame deserializes JSON bytes to a frame
func (fb *FrameBuilder) DeserializeFrame(data []byte) (Frame, error) {
	var frame Frame
	err := json.Unmarshal(data, &frame)
	return frame, err
}
