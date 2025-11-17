# ATP Documentation Index

**Complete navigation guide for all ATP platform documentation**

---

## 🚀 Getting Started

Perfect for new users looking to get ATP running quickly.

| Document | Description | When to Read |
|----------|-------------|--------------|
| [QUICK_START.md](QUICK_START.md) | Get ATP running in 5 minutes | **Start here** if you want to try ATP immediately |
| [GETTING_STARTED.md](GETTING_STARTED.md) | Complete step-by-step onboarding | Read after quick start for full understanding |
| [README.md](README.md) | Project overview and features | Reference for capabilities and examples |
| [AI_ASSISTANT_GUIDE.md](AI_ASSISTANT_GUIDE.md) | **Guide for AI assistants** helping users | **For AIs/bots** - Critical gotchas and decision trees |

---

## 📋 Configuration & Setup

Essential configuration guides for deploying and configuring ATP.

| Document | Description | When to Read |
|----------|-------------|--------------|
| [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) | **Complete** environment variable reference | **Critical** - Reference when configuring ATP |
| [.env.example](.env.example) | Environment variable template | Copy and customize for your deployment |
| [PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md) | Production deployment guide | Before deploying to production |

---

## 🔌 Adapters & Integration

Information about LLM adapters and their implementation status.

| Document | Description | When to Read |
|----------|-------------|--------------|
| [ADAPTER_STATUS.md](ADAPTER_STATUS.md) | **Which adapters work** vs. stubs | **Read before configuring adapters** |
| [docs/13_Adapter_Conformance_and_Testing.md](docs/13_Adapter_Conformance_and_Testing.md) | Adapter testing requirements | When implementing new adapters |
| [docs/14_MCP_Integration.md](docs/14_MCP_Integration.md) | Model Context Protocol integration | When using MCP features |

---

## 🛠️ CLI Tools

Documentation for the atpctl command-line interface.

| Document | Description | When to Read |
|----------|-------------|--------------|
| [tools/cli/README.md](tools/cli/README.md) | Complete CLI documentation | When using atpctl commands |
| [tools/cli/CLI_STATUS.md](tools/cli/CLI_STATUS.md) | **Which CLI commands work** | **Read before using CLI** to know limitations |

---

## 🏗️ Architecture & Specifications

Deep technical documentation about ATP's architecture and protocols.

| Document | Description | When to Read |
|----------|-------------|--------------|
| [docs/01_ATP.md](docs/01_ATP.md) | **ATP Protocol Specification** | For understanding core architecture |
| [docs/04_AGP_Federation_Spec.md](docs/04_AGP_Federation_Spec.md) | Federation specification | When implementing federation |
| [docs/05_Phase01_mvp.md](docs/05_Phase01_mvp.md) | MVP implementation plan | For development roadmap |
| [DEEP_DIVE_REVIEW.md](DEEP_DIVE_REVIEW.md) | Technical deep dive and review | For comprehensive technical understanding |

---

## 📚 Feature Guides

Detailed guides for specific ATP features.

### Storage & Memory
- [docs/artifact_tier_guide.md](docs/artifact_tier_guide.md) - Artifact storage
- [docs/vector_tier_guide.md](docs/vector_tier_guide.md) - Vector search
- [docs/graph_tier_guide.md](docs/graph_tier_guide.md) - Graph storage

### Routing & Optimization
- [docs/edge_routing_guide.md](docs/edge_routing_guide.md) - Edge routing
- [docs/carbon_aware_routing_guide.md](docs/carbon_aware_routing_guide.md) - Sustainability features
- [docs/multi_objective_scoring_guide.md](docs/multi_objective_scoring_guide.md) - Scoring algorithms

### Security & Policy
- [docs/security/SECURITY_CLEANUP_SUMMARY.md](docs/security/SECURITY_CLEANUP_SUMMARY.md) - Security overview
- [docs/enterprise_authentication.md](docs/enterprise_authentication.md) - Authentication setup
- [docs/policy_approval_workflow.md](docs/policy_approval_workflow.md) - Policy management
- [SECURITY.md](SECURITY.md) - Security policy

### Deployment & Operations
- [docs/on_prem_deployment_guide.md](docs/on_prem_deployment_guide.md) - On-premises deployment
- [docs/evidence_pack_assembler.md](docs/evidence_pack_assembler.md) - Evidence packing

---

## 🔬 Development & Contributing

Guides for developers contributing to ATP.

| Document | Description | When to Read |
|----------|-------------|--------------|
| [CONTRIBUTING.md](CONTRIBUTING.md) | **Contribution guidelines** | **Before contributing code** |
| [TODO.md](TODO.md) | Project roadmap and todos (104KB!) | For understanding future plans |
| [ENHANCEMENTS.md](ENHANCEMENTS.md) | Proposed enhancements | When planning features |
| [CHANGELOG.md](CHANGELOG.md) | Version history | When upgrading versions |

---

## 🐛 Troubleshooting & Support

Resources for debugging and getting help.

### Primary Troubleshooting Guide
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - **Comprehensive troubleshooting guide** with common issues, error messages, and fixes

### Validation & Testing
```bash
# Automated installation validation
python scripts/validate_installation.py --verbose

# Health checks
curl http://localhost:7443/healthz
curl http://localhost:8080/healthz
```

### Additional Troubleshooting Sections
- **[QUICK_START.md](QUICK_START.md#common-issues)** - Common startup issues
- **[GETTING_STARTED.md](GETTING_STARTED.md#troubleshooting)** - Detailed troubleshooting
- **[PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md#troubleshooting)** - Production issues

### Key Troubleshooting Files
- [scripts/validate_installation.py](scripts/validate_installation.py) - Comprehensive validation
- [client/health_check.py](client/health_check.py) - Quick health check
- Docker logs: `docker compose logs -f`

---

## 📊 Examples & Use Cases

Practical examples for common scenarios.

### Quick Examples
| File | Description |
|------|-------------|
| [client/health_check.py](client/health_check.py) | Health check example |
| [client/memory_put_get.py](client/memory_put_get.py) | Memory operations example |
| [client/mcp_cli.py](client/mcp_cli.py) | MCP client example |

### Use Case Documentation
- **[GETTING_STARTED.md](GETTING_STARTED.md#common-use-cases)** - Common use cases
- **[README.md](README.md#usage)** - Usage examples
- **[docs/01_ATP.md](docs/01_ATP.md)** - Protocol examples

---

## 🎯 Quick Reference by Task

### "I want to..."

#### ...get started quickly
1. Read [QUICK_START.md](QUICK_START.md)
2. Set `ROUTER_ADMIN_API_KEY` in `.env`
3. Run `docker compose up -d`

#### ...understand configuration
1. Read [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)
2. Check [.env.example](.env.example)
3. Reference [PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md)

#### ...add an LLM provider
1. Check [ADAPTER_STATUS.md](ADAPTER_STATUS.md) for available adapters
2. Configure adapter in `docker-compose.yml`
3. Set API keys in `.env`
4. **Note**: CLI provider management not yet functional (see [CLI_STATUS.md](tools/cli/CLI_STATUS.md))

#### ...deploy to production
1. Read [PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md)
2. Review [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) for required variables
3. Set up secrets management
4. Run `python scripts/validate_installation.py`

#### ...use the CLI
1. Read [tools/cli/README.md](tools/cli/README.md)
2. **Check** [tools/cli/CLI_STATUS.md](tools/cli/CLI_STATUS.md) **for command availability**
3. Set `ATP_API_URL=http://localhost:7443`
4. Try `atpctl chat repl`

#### ...contribute code
1. Read [CONTRIBUTING.md](CONTRIBUTING.md)
2. Check [TODO.md](TODO.md) for open tasks
3. Review [ENHANCEMENTS.md](ENHANCEMENTS.md) for ideas
4. Follow code quality guidelines

#### ...understand the architecture
1. Start with [docs/01_ATP.md](docs/01_ATP.md)
2. Read [DEEP_DIVE_REVIEW.md](DEEP_DIVE_REVIEW.md)
3. Check [docs/04_AGP_Federation_Spec.md](docs/04_AGP_Federation_Spec.md)
4. Review feature-specific guides in `docs/`

#### ...troubleshoot issues
1. Run `python scripts/validate_installation.py --verbose`
2. Check logs: `docker compose logs -f`
3. Review [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md#troubleshooting)
4. Check [GETTING_STARTED.md](GETTING_STARTED.md#troubleshooting)

---

## 📁 Documentation Directory Structure

```
atp-main/
├── README.md                          # Project overview
├── QUICK_START.md                     # 5-minute quick start ⭐ NEW
├── GETTING_STARTED.md                 # Complete onboarding
├── ENVIRONMENT_VARIABLES.md           # Complete config reference ⭐ NEW
├── DOCUMENTATION_INDEX.md             # This file ⭐ NEW
├── PRODUCTION_DEPLOYMENT_GUIDE.md     # Production deployment
├── ADAPTER_STATUS.md                  # Adapter implementation status
├── CONTRIBUTING.md                    # Development guidelines
├── CHANGELOG.md                       # Version history
├── TODO.md                            # Roadmap (104KB)
├── ENHANCEMENTS.md                    # Enhancement proposals
├── DEEP_DIVE_REVIEW.md               # Technical deep dive
├── SECURITY.md                        # Security policy
├── .env.example                       # Environment template
│
├── docs/                              # Detailed documentation
│   ├── 01_ATP.md                     # ATP specification
│   ├── 04_AGP_Federation_Spec.md     # Federation spec
│   ├── 05_Phase01_mvp.md             # MVP plan
│   ├── 14_MCP_Integration.md         # MCP integration
│   ├── 13_Adapter_Conformance_and_Testing.md
│   ├── architecture/                 # Architecture docs
│   ├── security/                     # Security docs
│   └── [30+ feature guides]          # Feature-specific docs
│
├── tools/cli/                         # CLI documentation
│   ├── README.md                     # CLI overview
│   └── CLI_STATUS.md                 # Command availability ⭐ NEW
│
├── scripts/                           # Utility scripts
│   └── validate_installation.py      # Installation validator
│
└── client/                            # Example scripts
    ├── health_check.py               # Health check
    ├── memory_put_get.py             # Memory operations
    └── mcp_cli.py                    # MCP client
```

---

## 🆕 Recently Added Documentation

### 2025-01-17 (Deep Dive Review Updates)
- ⭐ **TROUBLESHOOTING.md** - **NEW**: Comprehensive troubleshooting guide with common issues and fixes
- ⭐ **AI_ASSISTANT_GUIDE.md** - **NEW**: Critical guide for AI assistants helping users
- ⭐ **.env file** - **ADDED**: Now included in repository (was missing)
- 🔧 **QUICK_START.md** - Added critical warning about stub adapters
- 🔧 **Helm chart paths** - Fixed incorrect paths in GETTING_STARTED.md and DEEP_DIVE_REVIEW.md

### 2025-01-17 (Initial Documentation Improvements)
- ⭐ **QUICK_START.md** - New 5-minute quick start guide
- ⭐ **ENVIRONMENT_VARIABLES.md** - Complete environment variable reference
- ⭐ **DOCUMENTATION_INDEX.md** - This navigation guide
- ⭐ **tools/cli/CLI_STATUS.md** - CLI command availability status
- 🔧 **Port standardization** - All docs updated to use 7443 (not 8000)
- 🔧 **Fixed file paths** - Corrected Helm chart path and other references

---

## 📞 Getting Help

1. **Check Documentation**: Use this index to find relevant docs
2. **Run Validation**: `python scripts/validate_installation.py --verbose`
3. **Check Logs**: `docker compose logs -f`
4. **Review Issues**: Check for similar issues in GitHub
5. **Ask Questions**: Open a GitHub issue with details

---

## 🎓 Learning Path

### For New Users
1. [QUICK_START.md](QUICK_START.md) → Quick hands-on
2. [GETTING_STARTED.md](GETTING_STARTED.md) → Comprehensive guide
3. [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) → Configuration
4. [ADAPTER_STATUS.md](ADAPTER_STATUS.md) → Understand adapters

### For Developers
1. [CONTRIBUTING.md](CONTRIBUTING.md) → Development setup
2. [docs/01_ATP.md](docs/01_ATP.md) → Architecture
3. [DEEP_DIVE_REVIEW.md](DEEP_DIVE_REVIEW.md) → Technical details
4. [TODO.md](TODO.md) → Find tasks

### For Operators
1. [PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md) → Deployment
2. [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) → Configuration
3. [docs/security/](docs/security/) → Security
4. [scripts/validate_installation.py](scripts/validate_installation.py) → Validation

---

**Last Updated**: 2025-01-17

**Maintained by**: ATP Documentation Team

**Suggestions**: Open an issue or PR to improve this index
