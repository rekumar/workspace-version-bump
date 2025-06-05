# UV Workspace Version Bump Pre-commit Hook

This pre-commit hook automates version bumping for Python projects managed in a UV workspace (or similar monorepo structure with multiple `pyproject.toml` files).

## Features

- **Automatic Patch Version Bumping**: Identifies packages with staged changes and automatically increments their patch version if not already manually updated.
- **Root Project Bumping**: If any sub-packages are version bumped, the root project's `pyproject.toml` version is also bumped.
- **Configurable Package Directories**: Specify which directories contain your packages (e.g., `packages/`, `libs/`).
- **Ignore Specific Packages**: Exclude certain packages from automatic version bumping.
- **Custom Root Project Path**: Define a custom path for your main `pyproject.toml` if it's not in the repository root.
- **Respects Manual Bumps**: If a version is manually changed and staged in a `pyproject.toml`, this hook will not override it.
- **Handles Standard and Poetry `pyproject.toml`**: Detects version numbers in `[project.version]` or `[tool.poetry.version]`.

## How it Works

The hook performs the following steps when you run `git commit`:

1.  **Parses Arguments**: Reads configuration for package directories, ignored packages, and root project path.
2.  **Identifies Staged Files**: Uses `git diff --cached --name-only` to find all files staged for commit.
3.  **Detects Changed Packages**: Determines which packages (subdirectories with a `pyproject.toml`) within the configured `package_dirs` have staged changes.
4.  **Filters Ignored Packages**: Removes any packages from the changed list that are specified in `--ignore-packages`.
5.  **Checks for Manual Version Updates**:
    *   For each changed package, it compares the version in its staged `pyproject.toml` (if any) against the version in `HEAD`.
    *   If a package's version was manually changed and staged, the hook acknowledges this and skips auto-bumping for that package.
6.  **Auto-Bumps Patch Version**: If a changed package's version was not manually updated, the hook increments its patch version (e.g., `0.1.0` → `0.1.1`).
7.  **Updates `pyproject.toml`**: Writes the new version back to the package's `pyproject.toml` file.
8.  **Stages Changes**: Uses `git add` to stage the modified `pyproject.toml` files.
9.  **Bumps Root Version**: If any packages were bumped (either automatically or manually acknowledged), the hook then checks the root `pyproject.toml`:
    *   It performs a similar check for manual updates to the root version.
    *   If not manually updated, it increments the root project's patch version and stages the change.

If any `pyproject.toml` files are modified by the hook, these changes will be included in the current commit.

## Installation and Usage

1.  **Add this repository to your `.pre-commit-config.yaml`:**

    ```yaml
    repos:
      - repo: https://github.com/your-username/your-repo-name # Replace with YOUR repository URL
        rev: v0.1.0  # Use the latest tag or a specific commit hash
        hooks:
          - id: version-bump
            args:
              # Optional: Specify directories containing your packages
              # Default is ["packages"]
              - "--package-dirs"
              - "packages"
              - "libs" # Example: if you also have a 'libs' directory

              # Optional: Specify package names (directory names) to ignore
              # - "--ignore-packages"
              # - "internal_utils"
              # - "docs_generator"

              # Optional: Specify the path to your root pyproject.toml
              # Default is "pyproject.toml" (in the repo root)
              # - "--root-pyproject-path"
              # - "my_main_app/pyproject.toml"

              # Optional: Whether to skip version bumps in the root pyproject.toml
              # - "--dont-bump-root"
    ```

2.  **Install pre-commit hooks:**

    ```bash
    pre-commit install
    ```

Now, the `version-bump` hook will run automatically each time you commit changes.

## Configuration Arguments

The hook can be configured via the `args` section in your `.pre-commit-config.yaml`:

-   `--package-dirs <dir1> [<dir2> ...]`
    -   One or more directory names that contain your packages. Each immediate subdirectory within these directories that contains a `pyproject.toml` is considered a package.
    -   Default: `["packages"]`
    -   Example: `args: ["--package-dirs", "packages", "components"]`

-   `--ignore-packages <pkg_name1> [<pkg_name2> ...]`
    -   A list of package names (the directory names of the packages, not their paths) to exclude from version bumping.
    -   Default: `[]` (empty list)
    -   Example: `args: ["--ignore-packages", "my_utility_lib", "experimental_feature"]`

-   `--root-pyproject-path <path>`
    -   The path to the root `pyproject.toml` file of your workspace/monorepo.
    -   Default: `"pyproject.toml"` (relative to the repository root)
    -   Example: `args: ["--root-pyproject-path", "./src/my_project/pyproject.toml"]`

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

If you plan to contribute, consider setting up pre-commit for this repository as well:

```bash
# (After cloning the repo)
python -m venv .venv
source .venv/bin/activate
pip install pre-commit toml
pre-commit install
```

## License

This project is licensed under the MIT License - see the `LICENSE` file for details (you may want to add one!). 