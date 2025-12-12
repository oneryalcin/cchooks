# Publishing a New Release

## Steps

```bash
# 1. Update version in pyproject.toml
# e.g., version = "0.1.4"

# 2. Commit and tag
git add pyproject.toml
git commit -m "Bump version to 0.1.4"
git tag v0.1.4

# 3. Push (triggers auto-release on GitHub)
git push && git push --tags

# 4. Build and publish to PyPI
uv build && uv publish --token "$PYPI_TOKEN"
```

## What Happens

- **GitHub**: Auto-creates release with changelog via `.github/workflows/release.yml`
- **PyPI**: Package published, badge auto-updates
- **Docs**: No action needed (deploys on main push)

## Verify

```bash
# Check PyPI
curl -s https://pypi.org/pypi/fasthooks/json | python3 -c "import sys,json; print(json.load(sys.stdin)['info']['version'])"

# Check GitHub release
gh release view v0.1.4
```
