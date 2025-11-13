// Package atpsdk provides a Go client for the ATP Router protocol
package atpsdk

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

// SDKConfig holds configuration for the ATP SDK
type SDKConfig struct {
	BaseURL         string
	WSURL           string
	APIKey          string
	TenantID        string
	SessionID       string
	DefaultTimeout  time.Duration
	MaxRetries      int
	RetryDelay      time.Duration
	HeartbeatInterval time.Duration
}

// Frame represents an ATP protocol frame
type Frame struct {
	Type      string                 `json:"type"`
	Timestamp int64                  `json:"ts"`
	StreamID  string                 `json:"stream_id,omitempty"`
	MsgSeq    int                    `json:"msg_seq,omitempty"`
	FragSeq   int                    `json:"frag_seq,omitempty"`
	Flags     []string               `json:"flags,omitempty"`
	QoS       string                 `json:"qos,omitempty"`
	TTL       int                    `json:"ttl,omitempty"`
	Window    Window                 `json:"window,omitempty"`
	Meta      Meta                   `json:"meta,omitempty"`
	Payload   map[string]interface{} `json:"payload"`
}

// Window represents flow control window information
type Window struct {
	MaxParallel  int `json:"max_parallel"`
	MaxTokens    int `json:"max_tokens"`
	MaxUSD       int `json:"max_usd_micros"`
}

// Meta contains metadata for the frame
type Meta struct {
	TaskType       string            `json:"task_type,omitempty"`
	Languages      []string          `json:"languages,omitempty"`
	Risk           string            `json:"risk,omitempty"`
	DataScope      []string          `json:"data_scope,omitempty"`
	Trace          interface{}       `json:"trace,omitempty"`
	ToolPermissions []string         `json:"tool_permissions,omitempty"`
	EnvironmentID  string            `json:"environment_id,omitempty"`
	SecurityGroups []string          `json:"security_groups,omitempty"`
}

// CompletionRequest represents a completion request
type CompletionRequest struct {
	Prompt      string  `json:"prompt"`
	MaxTokens   int     `json:"max_tokens,omitempty"`
	Temperature float64 `json:"temperature,omitempty"`
	TopP        float64 `json:"top_p,omitempty"`
	Stop        []string `json:"stop,omitempty"`
}

// CompletionResponse represents a completion response
type CompletionResponse struct {
	Text        string  `json:"text"`
	ModelUsed   string  `json:"model_used"`
	TokensIn    int     `json:"tokens_in"`
	TokensOut   int     `json:"tokens_out"`
	CostUSD     float64 `json:"cost_usd"`
	QualityScore float64 `json:"quality_score"`
	Finished    bool    `json:"finished"`
}

// CapabilityAdvertisement represents an adapter's capability advertisement
type CapabilityAdvertisement struct {
	AdapterID          string            `json:"adapter_id"`
	AdapterType        string            `json:"adapter_type"`
	Capabilities       []string          `json:"capabilities"`
	Models             []string          `json:"models"`
	MaxTokens          *int              `json:"max_tokens,omitempty"`
	SupportedLanguages []string          `json:"supported_languages,omitempty"`
	CostPerTokenMicros *int              `json:"cost_per_token_micros,omitempty"`
	HealthEndpoint     *string           `json:"health_endpoint,omitempty"`
	Version            *string           `json:"version,omitempty"`
	Metadata           map[string]interface{} `json:"metadata,omitempty"`
}

// HealthStatus represents an adapter's health status and telemetry
type HealthStatus struct {
	AdapterID          string                 `json:"adapter_id"`
	Status             string                 `json:"status"`
	P95LatencyMS       *float64               `json:"p95_latency_ms,omitempty"`
	P50LatencyMS       *float64               `json:"p50_latency_ms,omitempty"`
	P99LatencyMS       *float64               `json:"p99_latency_ms,omitempty"`
	RequestsPerSecond  *float64               `json:"requests_per_second,omitempty"`
	ErrorRate          *float64               `json:"error_rate,omitempty"`
	QueueDepth         *int                   `json:"queue_depth,omitempty"`
	MemoryUsageMB      *float64               `json:"memory_usage_mb,omitempty"`
	CPUUsagePercent    *float64               `json:"cpu_usage_percent,omitempty"`
	UptimeSeconds      *int                   `json:"uptime_seconds,omitempty"`
	Version            *string                `json:"version,omitempty"`
	LastHealthCheck    *float64               `json:"last_health_check,omitempty"`
	Metadata           map[string]interface{} `json:"metadata,omitempty"`
}

// ATPClient is the main client for interacting with ATP Router
type ATPClient struct {
	config     SDKConfig
	conn       *websocket.Conn
	connMutex  sync.RWMutex
	connected  bool
	responseHandlers map[string]chan *Frame
	handlerMutex     sync.RWMutex
	ctx             context.Context
	cancel          context.CancelFunc
}

// NewATPClient creates a new ATP client with the given configuration
func NewATPClient(config SDKConfig) *ATPClient {
	if config.BaseURL == "" {
		config.BaseURL = "http://localhost:8000"
	}
	if config.WSURL == "" {
		config.WSURL = "ws://localhost:8000"
	}
	if config.TenantID == "" {
		config.TenantID = "default"
	}
	if config.SessionID == "" {
		config.SessionID = fmt.Sprintf("session_%d_%d", time.Now().Unix(), time.Now().Nanosecond())
	}
	if config.DefaultTimeout == 0 {
		config.DefaultTimeout = 30 * time.Second
	}
	if config.MaxRetries == 0 {
		config.MaxRetries = 3
	}
	if config.RetryDelay == 0 {
		config.RetryDelay = time.Second
	}
	if config.HeartbeatInterval == 0 {
		config.HeartbeatInterval = 30 * time.Second
	}

	ctx, cancel := context.WithCancel(context.Background())

	return &ATPClient{
		config:          config,
		responseHandlers: make(map[string]chan *Frame),
		ctx:             ctx,
		cancel:          cancel,
	}
}

// Connect establishes a WebSocket connection to the ATP Router
func (c *ATPClient) Connect() error {
	c.connMutex.Lock()
	defer c.connMutex.Unlock()

	if c.connected {
		return nil
	}

	// Parse WebSocket URL
	wsURL, err := url.Parse(c.config.WSURL)
	if err != nil {
		return fmt.Errorf("invalid WebSocket URL: %w", err)
	}

	// Add query parameters
	query := wsURL.Query()
	query.Set("session_id", c.config.SessionID)
	query.Set("tenant_id", c.config.TenantID)
	if c.config.APIKey != "" {
		query.Set("api_key", c.config.APIKey)
	}
	wsURL.RawQuery = query.Encode()

	// Connect to WebSocket
	conn, _, err := websocket.DefaultDialer.Dial(wsURL.String(), nil)
	if err != nil {
		return fmt.Errorf("failed to connect to WebSocket: %w", err)
	}

	c.conn = conn
	c.connected = true

	// Start message handling goroutine
	go c.handleMessages()

	// Start heartbeat goroutine
	go c.sendHeartbeats()

	return nil
}

// Disconnect closes the WebSocket connection
func (c *ATPClient) Disconnect() error {
	c.connMutex.Lock()
	defer c.connMutex.Unlock()

	if !c.connected {
		return nil
	}

	c.cancel() // Cancel context to stop goroutines
	c.connected = false

	if c.conn != nil {
		err := c.conn.Close()
		c.conn = nil
		return err
	}

	return nil
}

// IsConnected returns whether the client is connected
func (c *ATPClient) IsConnected() bool {
	c.connMutex.RLock()
	defer c.connMutex.RUnlock()
	return c.connected
}

// Complete sends a completion request and waits for response
func (c *ATPClient) Complete(ctx context.Context, request CompletionRequest) (*CompletionResponse, error) {
	if !c.IsConnected() {
		if err := c.Connect(); err != nil {
			return nil, fmt.Errorf("failed to connect: %w", err)
		}
	}

	streamID := fmt.Sprintf("completion_%d_%d", time.Now().Unix(), time.Now().Nanosecond())

	// Create frame builder if not exists
	frameBuilder := NewFrameBuilder(c.config.SessionID, c.config.TenantID)
	frame := frameBuilder.BuildCompletionFrame(streamID, request)

	// Send frame
	if err := c.sendFrame(frame); err != nil {
		return nil, fmt.Errorf("failed to send frame: %w", err)
	}

	// Wait for response
	responseFrame, err := c.waitForResponse(ctx, streamID, frame.MsgSeq)
	if err != nil {
		return nil, fmt.Errorf("failed to get response: %w", err)
	}

	// Parse response
	return c.parseCompletionResponse(responseFrame)
}

// AdvertiseCapabilities sends a capability advertisement to the ATP Router
func (c *ATPClient) AdvertiseCapabilities(ctx context.Context, capability CapabilityAdvertisement) error {
	if !c.IsConnected() {
		if err := c.Connect(); err != nil {
			return fmt.Errorf("failed to connect: %w", err)
		}
	}

	streamID := fmt.Sprintf("capability_%d_%d", time.Now().Unix(), time.Now().Nanosecond())

	// Create frame builder if not exists
	frameBuilder := NewFrameBuilder(c.config.SessionID, c.config.TenantID)
	frame := frameBuilder.BuildCapabilityFrame(streamID, capability)

	// Send frame
	if err := c.sendFrame(frame); err != nil {
		return fmt.Errorf("failed to send capability frame: %w", err)
	}

	// Wait for acknowledgment (optional - could be fire-and-forget)
	_, err := c.waitForResponse(ctx, streamID, frame.MsgSeq)
	if err != nil {
		// Log warning but don't fail - capability advertisement is often fire-and-forget
		fmt.Printf("Warning: No acknowledgment received for capability advertisement: %v\n", err)
	}

	return nil
}

// ReportHealth sends a health status update to the ATP Router
func (c *ATPClient) ReportHealth(ctx context.Context, health HealthStatus) error {
	if !c.IsConnected() {
		if err := c.Connect(); err != nil {
			return fmt.Errorf("failed to connect: %w", err)
		}
	}

	streamID := fmt.Sprintf("health_%d_%d", time.Now().Unix(), time.Now().Nanosecond())

	// Create frame builder if not exists
	frameBuilder := NewFrameBuilder(c.config.SessionID, c.config.TenantID)
	frame := frameBuilder.BuildHealthFrame(streamID, health)

	// Send frame
	if err := c.sendFrame(frame); err != nil {
		return fmt.Errorf("failed to send health frame: %w", err)
	}

	// Wait for acknowledgment (optional - could be fire-and-forget)
	_, err := c.waitForResponse(ctx, streamID, frame.MsgSeq)
	if err != nil {
		// Log warning but don't fail - health reports are often fire-and-forget
		fmt.Printf("Warning: No acknowledgment received for health report: %v\n", err)
	}

	return nil
}

// sendFrame sends a frame over the WebSocket connection
func (c *ATPClient) sendFrame(frame Frame) error {
	c.connMutex.RLock()
	defer c.connMutex.RUnlock()

	if !c.connected || c.conn == nil {
		return fmt.Errorf("not connected")
	}

	data, err := json.Marshal(frame)
	if err != nil {
		return fmt.Errorf("failed to marshal frame: %w", err)
	}

	return c.conn.WriteMessage(websocket.TextMessage, data)
}

// waitForResponse waits for a response frame with the given stream ID and message sequence
func (c *ATPClient) waitForResponse(ctx context.Context, streamID string, msgSeq int) (*Frame, error) {
	requestID := fmt.Sprintf("%s:%d", streamID, msgSeq)

	// Create response channel
	responseChan := make(chan *Frame, 1)

	c.handlerMutex.Lock()
	c.responseHandlers[requestID] = responseChan
	c.handlerMutex.Unlock()

	defer func() {
		c.handlerMutex.Lock()
		delete(c.responseHandlers, requestID)
		c.handlerMutex.Unlock()
	}()

	// Wait for response with timeout
	select {
	case response := <-responseChan:
		return response, nil
	case <-ctx.Done():
		return nil, ctx.Err()
	case <-time.After(c.config.DefaultTimeout):
		return nil, fmt.Errorf("request timeout")
	}
}

// parseCompletionResponse parses a completion response frame
func (c *ATPClient) parseCompletionResponse(frame *Frame) (*CompletionResponse, error) {
	if frame.Type == "error" {
		if payload, ok := frame.Payload["error"].(map[string]interface{}); ok {
			if msg, ok := payload["message"].(string); ok {
				return nil, fmt.Errorf("ATP Router error: %s", msg)
			}
		}
		return nil, fmt.Errorf("ATP Router error: unknown error")
	}

	payload := frame.Payload
	response := &CompletionResponse{
		Text:         getString(payload, "text", ""),
		ModelUsed:    getString(payload, "model_used", "unknown"),
		TokensIn:     getInt(payload, "tokens_in", 0),
		TokensOut:    getInt(payload, "tokens_out", 0),
		CostUSD:      getFloat64(payload, "cost_usd", 0),
		QualityScore: getFloat64(payload, "quality_score", 0),
		Finished:     true,
	}

	return response, nil
}

// handleMessages handles incoming WebSocket messages
func (c *ATPClient) handleMessages() {
	for {
		select {
		case <-c.ctx.Done():
			return
		default:
			if !c.IsConnected() {
				time.Sleep(time.Second)
				continue
			}

			_, data, err := c.conn.ReadMessage()
			if err != nil {
				// Connection error - could implement reconnection logic here
				continue
			}

			var frame Frame
			if err := json.Unmarshal(data, &frame); err != nil {
				// Invalid frame - could emit error event
				continue
			}

			// Handle response frames
			if frame.Type == "completion_response" || frame.Type == "error" {
				requestID := fmt.Sprintf("%s:%d", frame.StreamID, frame.MsgSeq)
				c.handlerMutex.RLock()
				if handler, exists := c.responseHandlers[requestID]; exists {
					select {
					case handler <- &frame:
					default:
						// Channel full, skip
					}
				}
				c.handlerMutex.RUnlock()
			}
		}
	}
}

// sendHeartbeats sends periodic heartbeat messages
func (c *ATPClient) sendHeartbeats() {
	ticker := time.NewTicker(c.config.HeartbeatInterval)
	defer ticker.Stop()

	for {
		select {
		case <-c.ctx.Done():
			return
		case <-ticker.C:
			if c.IsConnected() {
				frameBuilder := NewFrameBuilder(c.config.SessionID, c.config.TenantID)
				heartbeat := frameBuilder.BuildHeartbeatFrame()
				_ = c.sendFrame(heartbeat) // Ignore errors for heartbeat
			}
		}
	}
}

// Helper functions for safe type assertions
func getString(m map[string]interface{}, key, defaultValue string) string {
	if val, ok := m[key].(string); ok {
		return val
	}
	return defaultValue
}

func getInt(m map[string]interface{}, key string, defaultValue int) int {
	if val, ok := m[key].(float64); ok {
		return int(val)
	}
	return defaultValue
}

func getFloat64(m map[string]interface{}, key string, defaultValue float64) float64 {
	if val, ok := m[key].(float64); ok {
		return val
	}
	return defaultValue
}
