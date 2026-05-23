# Sandbox containers use writable root filesystem

The plan originally specified `--read-only` root filesystem with tmpfs for /tmp, assuming all packages are installed at image build time. We reversed this decision: the container root filesystem is writable so agents can install packages at runtime.

The security trade-off is accepted because:
- Package installation is a core agent capability (agents frequently need libraries not in the base image)
- The alternative (pre-installing every possible package) is infeasible
- Per-session volumes already persist installed state across container stop/start
- cap_drop and no-new-privileges still apply

If stronger isolation is needed later, a read-only root with user-space package paths (PYTHONUSERBASE, npm_config_prefix) is the next step.
