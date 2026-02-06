# Git Repository Setup Instructions

## Initialize Repository (Already Done)

The repository has been initialized with initial commit.

## Next Steps

### 1. Create Remote Repository

Create a new repository on GitHub/GitLab:

```bash
# Using GitHub CLI (if available)
gh repo create mcproxy --public --description "Lightweight MCP Gateway Aggregator" --source=.

# Or manually:
# 1. Go to https://github.com/new
# 2. Name repository: mcproxy
# 3. Description: Lightweight MCP Gateway Aggregator
# 4. Initialize with README: UNCHECK
# 5. Click "Create repository"
```

### 2. Add Remote

```bash
# Replace <username> with your GitHub/GitLab username
git remote add origin https://github.com/<username>/mcproxy.git

# Or if using SSH:
git remote add origin git@github.com:<username>/mcproxy.git
```

### 3. Push to Remote

```bash
# Push to main branch
git push -u origin master

# Or rename branch to main first:
git branch -m master main
git push -u origin main
```

### 4. Create Tags (Optional)

```bash
# Tag current version
git tag -a v1.0 -m "MCProxy v1.0 - Production Release"

# Push tags
git push origin --tags
```

---

## Repository Structure

```
mcproxy/
├── .gitignore                    # Git ignore rules
├── .env.example                  # Environment variables template
├── README.md                     # Main documentation
├── AGENTS.md                     # Agent guidelines
├── mcproxy_spec.md               # Technical specification
├── mcproxy_implementation_guide.md # Implementation guide
├── mcproxy_decision_summary.md     # Decision rationale
├── requirements.txt               # Python dependencies
├── Dockerfile                    # Multi-stage container build
├── mcproxy.container             # Podman quadlet
├── podman-compose.yml            # Compose deployment
├── setup.sh                     # Local development setup
├── deploy.sh                    # Remote deployment script
├── mcp-servers.example.json      # Example server config
└── *.py                         # Python modules
    ├── main.py
    ├── server.py
    ├── server_manager.py
    ├── config_watcher.py
    ├── config_reloader.py
    ├── tool_aggregator.py
    ├── logging_config.py
    └── test_server.py
```

---

## Usage Examples

### For Developers

```bash
# Clone repository
git clone https://github.com/<username>/mcproxy.git
cd mcproxy

# Setup local environment
./setup.sh

# Run in development mode
source venv/bin/activate
python main.py --log --port 12010
```

### For Production Deployment

```bash
# Clone repository
git clone https://github.com/<username>/mcproxy.git
cd mcproxy

# Deploy to remote server
./deploy.sh server2-auto

# Or manually:
ssh server2-auto
cd /srv/containers/mc-gateway
git clone https://github.com/<username>/mcproxy.git .
./setup.sh
```

### Container Deployment

```bash
# Clone repository
git clone https://github.com/<username>/mcproxy.git
cd mcproxy

# Using Podman Compose
podman-compose up -d

# Or using Quadlet
cp mcproxy.container /etc/containers/systemd/mcproxy.container
sudo systemctl daemon-reload
sudo systemctl start mcproxy.service
```

---

## Branch Naming

Current default: `master`

Recommended for new repositories: `main`

To rename branch:

```bash
git branch -m master main
git push -u origin main
```

---

## Tagging Strategy

Use semantic versioning: `vX.Y.Z`

- **X**: Major version (breaking changes)
- **Y**: Minor version (new features)
- **Z**: Patch version (bug fixes)

Examples:
- `v1.0.0` - Initial production release
- `v1.1.0` - Added hot-reload feature
- `v1.1.1` - Fixed memory leak bug

---

## Pull Request Workflow

```bash
# 1. Create feature branch
git checkout -b feature/new-feature

# 2. Make changes
# ... edit files ...

# 3. Commit changes
git add .
git commit -m "Add new feature"

# 4. Push to remote
git push -u origin feature/new-feature

# 5. Create pull request on GitHub/GitLab
```

---

## CI/CD (Future)

Consider adding:
- `.github/workflows/test.yml` - Run tests on push
- `.github/workflows/docker.yml` - Build and push Docker images
- `.github/workflows/deploy.yml` - Deploy to production on merge

---

## License

MIT License - See LICENSE file (to be added)

---

## Questions?

For support or questions, see:
- Main documentation: README.md
- Technical specs: mcproxy_spec.md
- Agent guidelines: AGENTS.md
