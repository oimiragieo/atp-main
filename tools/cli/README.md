# ATP Control CLI (atpctl)

World-class enterprise command-line interface for managing the ATP (Adaptive Text Processing) platform.

## Features

### 🚀 **Interactive AI Chat & REPL**
- **Claude CLI-like experience** with rich, interactive chat interface
- Full conversation history and session management
- Multiline input support
- Auto-complete and command suggestions
- Markdown rendering for beautiful responses
- Session save/load/export functionality

### 🎯 **Platform Management**
- **Cluster Management**: Scale, monitor, and manage cluster nodes
- **Provider Management**: Configure and manage AI model providers (OpenAI, Anthropic, Google, etc.)
- **Policy Management**: Create and enforce rate limits, cost controls, and content filters
- **Configuration Management**: Import/export/validate system configuration
- **System Monitoring**: Real-time metrics, logs, and health checks

### 💡 **Advanced Features**
- Multiple output formats (table, JSON, YAML)
- Rich terminal UI with colors and panels
- Streaming log support
- Interactive confirmations for destructive operations
- Shell completion support (coming soon)

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Install atpctl globally (optional)
pip install -e tools/cli
```

## Quick Start

### Interactive Chat (REPL)
```bash
# Start interactive chat session
atpctl chat repl

# Ask a quick question
atpctl chat ask "What is the capital of France?"

# Use specific model
atpctl chat repl --model gpt-4

# Enable multiline mode
atpctl chat repl --multiline
```

### Platform Management
```bash
# Check platform status
atpctl status

# List providers
atpctl providers list

# Add new provider
atpctl providers add openai --api-key YOUR_KEY

# View system metrics
atpctl system metrics

# Manage cluster
atpctl cluster list
atpctl cluster scale 3
```

### Configuration
```bash
# Show current config
atpctl config show

# Set config value
atpctl config set max_requests_per_minute 1000

# Export configuration
atpctl config export config.yaml

# Validate configuration
atpctl config validate
```

## Chat Commands

When in interactive REPL mode (`atpctl chat repl`), you can use:

- `/help` - Show available commands
- `/exit` - Exit chat session
- `/clear` - Clear conversation history
- `/save` - Save current session
- `/history` - Show conversation history
- `/export` - Export conversation to markdown
- `/multiline` - Toggle multiline input mode

## Environment Variables

```bash
# ATP API configuration
export ATP_API_URL="http://localhost:8000"
export ATP_API_KEY="your-api-key"

# CORS configuration (for server)
export CORS_ALLOWED_ORIGINS="http://localhost:3000,http://localhost:8080"
```

## Examples

### Example 1: Complete AI Workflow
```bash
# Start ATP router service
python -m router_service.main

# Configure provider in another terminal
atpctl providers add anthropic --api-key $ANTHROPIC_API_KEY --priority 10

# Start chatting
atpctl chat repl --model claude-3-5-sonnet-20241022

# In the REPL
You: Help me write a Python function to calculate Fibonacci numbers
Assistant: [Detailed response with code]

You: Can you optimize it?
Assistant: [Optimized version]

# Save and export
/save
/export
```

### Example 2: Monitor and Scale
```bash
# Check system health
atpctl system health

# View metrics
atpctl system metrics --interval 300

# Scale cluster based on load
atpctl cluster scale 5 --component router

# Monitor logs
atpctl system logs --follow --level INFO
```

### Example 3: Policy Management
```bash
# Create rate limit policy
cat > rate_limit.yaml <<EOF
name: api_rate_limit
type: rate_limit
rules:
  - max_requests_per_minute: 100
    max_requests_per_hour: 1000
EOF

atpctl policies add rate-limit-policy rate_limit --config rate_limit.yaml

# Test the policy
atpctl policies test rate-limit-policy

# Monitor policy stats
atpctl policies stats rate-limit-policy
```

## Architecture

```
atpctl/
├── commands/           # Command modules
│   ├── chat.py        # Interactive chat & REPL ⭐ NEW
│   ├── cluster.py     # Cluster management
│   ├── providers.py   # Provider management
│   ├── policies.py    # Policy management
│   ├── system.py      # System commands
│   └── config.py      # Configuration management
├── utils/             # Utility modules
│   ├── api_client.py  # ATP API client
│   ├── formatters.py  # Output formatters
│   └── validators.py  # Input validators
└── main.py            # CLI entry point
```

## Comparison with Claude CLI

| Feature | ATP CLI | Claude CLI |
|---------|---------|------------|
| Interactive REPL | ✅ | ✅ |
| Conversation History | ✅ | ✅ |
| Session Management | ✅ | ✅ |
| Multi-provider Support | ✅ | ❌ |
| Enterprise Features | ✅ | ❌ |
| Cost Optimization | ✅ | ❌ |
| Cluster Management | ✅ | ❌ |
| Policy Enforcement | ✅ | ❌ |
| Rich Terminal UI | ✅ | ✅ |

## Contributing

Contributions are welcome! Please ensure:
- Code is formatted with `ruff format`
- All tests pass with `pytest`
- Security issues are addressed
- Documentation is updated

## License

Apache License 2.0 - See LICENSE file for details
