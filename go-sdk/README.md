# ATP Go SDK Quickstart

The ATP Go SDK provides a client for interacting with the ATP Router protocol over WebSocket connections.

## Installation

```bash
go get github.com/atp-project/atp-go-sdk
```

## Basic Usage

```go
package main

import (
    "context"
    "fmt"
    "log"
    "time"

    "github.com/atp-project/atp-go-sdk"
)

func main() {
    // Create a new ATP client
    client := atpsdk.NewATPClient(atpsdk.SDKConfig{
        BaseURL:  "http://localhost:8000",
        WSURL:    "ws://localhost:8000",
        APIKey:   "your-api-key",
        TenantID: "your-tenant-id",
    })

    // Create a completion request
    request := atpsdk.CompletionRequest{
        Prompt:      "Write a hello world program in Go",
        MaxTokens:   100,
        Temperature: 0.7,
    }

    // Set up a context with timeout
    ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
    defer cancel()

    // Send the completion request
    response, err := client.Complete(ctx, request)
    if err != nil {
        log.Fatalf("Failed to complete: %v", err)
    }

    // Print the response
    fmt.Printf("Response: %s\n", response.Text)
    fmt.Printf("Model: %s\n", response.ModelUsed)
    fmt.Printf("Tokens: %d in, %d out\n", response.TokensIn, response.TokensOut)

    // Disconnect when done
    client.Disconnect()
}
```

## Configuration Options

The `SDKConfig` struct supports the following options:

```go
type SDKConfig struct {
    BaseURL           string        // HTTP base URL (default: "http://localhost:8000")
    WSURL             string        // WebSocket URL (default: "ws://localhost:8000")
    APIKey            string        // API key for authentication
    TenantID          string        // Tenant identifier (default: "default")
    SessionID         string        // Session identifier (auto-generated if empty)
    DefaultTimeout    time.Duration // Default request timeout (default: 30s)
    MaxRetries        int           // Maximum retry attempts (default: 3)
    RetryDelay        time.Duration // Delay between retries (default: 1s)
    HeartbeatInterval time.Duration // Heartbeat interval (default: 30s)
}
```

## Advanced Usage

### Manual Connection Management

```go
client := atpsdk.NewATPClient(config)

// Explicitly connect
if err := client.Connect(); err != nil {
    log.Fatalf("Failed to connect: %v", err)
}

// Check connection status
if client.IsConnected() {
    fmt.Println("Connected to ATP Router")
}

// Disconnect
client.Disconnect()
```

### Frame Builder

For advanced use cases, you can use the FrameBuilder directly:

```go
// Create a frame builder
fb := atpsdk.NewFrameBuilder("session-123", "tenant-456")

// Build a completion request frame
request := atpsdk.CompletionRequest{
    Prompt: "Explain quantum computing",
    MaxTokens: 200,
}
frame := fb.BuildCompletionFrame("stream-1", request)

// Serialize the frame
data, err := fb.SerializeFrame(frame)
if err != nil {
    log.Fatalf("Failed to serialize: %v", err)
}

// Deserialize a frame
var deserializedFrame atpsdk.Frame
err = fb.DeserializeFrame(data, &deserializedFrame)
```

### Error Handling

The SDK provides structured error handling:

```go
response, err := client.Complete(ctx, request)
if err != nil {
    switch e := err.(type) {
    case *atpsdk.ATPClientError:
        fmt.Printf("ATP Router error: %s\n", e.Message)
    default:
        fmt.Printf("Other error: %v\n", err)
    }
    return
}
```

## Testing

Run the test suite:

```bash
go test ./...
```

Run with verbose output:

```bash
go test -v ./...
```

Run benchmarks:

```bash
go test -bench=. ./...
```

## Concurrency

The ATP Go SDK is designed to be safe for concurrent use:

```go
var wg sync.WaitGroup
numRequests := 10

for i := 0; i < numRequests; i++ {
    wg.Add(1)
    go func(id int) {
        defer wg.Done()

        request := atpsdk.CompletionRequest{
            Prompt: fmt.Sprintf("Generate a story about robot %d", id),
        }

        response, err := client.Complete(ctx, request)
        if err != nil {
            log.Printf("Request %d failed: %v", id, err)
            return
        }

        fmt.Printf("Robot %d story: %s\n", id, response.Text)
    }(i)
}

wg.Wait()
```

## Logging

The SDK uses standard Go logging. You can control log output by setting the log level:

```go
import "log"

log.SetFlags(log.LstdFlags | log.Lshortfile)
```

## Troubleshooting

### Connection Issues

- Ensure the ATP Router is running and accessible
- Check that the WebSocket URL is correct
- Verify API key and tenant ID are valid

### Timeout Issues

- Increase the `DefaultTimeout` in SDKConfig
- Check network connectivity
- Monitor ATP Router performance

### Memory Usage

- The SDK maintains connection state and response handlers
- Call `Disconnect()` when done to clean up resources
- Use contexts with timeouts to prevent resource leaks

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass: `go test ./...`
5. Run linting: `golangci-lint run`
6. Submit a pull request

## License

This project is licensed under the MIT License.
