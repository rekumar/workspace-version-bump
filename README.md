# UV Workspace Version Bump Pre-commit Hook

This pre-commit hook automates version bumping for Python projects managed in a UV workspace (or similar monorepo structure with multiple `pyproject.toml` files). It uses `tomlkit` to parse and write `pyproject.toml` files, ensuring that comments, formatting, and key order are preserved as much as possible.

## Features

- **Automatic Patch Version Bumping**: Identifies packages with staged changes and automatically increments their patch version if not already manually updated.
- **Flexible Package Discovery**: Scans the entire repository for `pyproject.toml` files to identify packages.
- **Root Project Bumping (Optional)**: If any sub-packages are version bumped, the root project's `pyproject.toml` version is also bumped by default. This can be disabled.
- **Configurable Ignored Directories (Regex)**: Specify a list of regular expression patterns to ignore directories containing `pyproject.toml` files.
- **Custom Root Project Path**: Define a custom path for your main `pyproject.toml` if it's not in the repository root.
- **Respects Manual Bumps**: If a version is manually changed and staged in a `pyproject.toml`, this hook will not override it.
- **Handles Standard and Poetry `pyproject.toml`**: Detects version numbers in `[project.version]` or `[tool.poetry.version]`.
- **Preserves Formatting**: Uses `tomlkit` to ensure that your `pyproject.toml` files retain their original formatting and comments after version bumping.

## How it Works

The hook performs the following steps when you run `git commit`:

1.  **Parses Arguments**: Reads configuration for ignored directory regex patterns, root project path, and whether to bump the root project.
2.  **Scans for `pyproject.toml` Files**: Uses `Path.cwd().rglob('pyproject.toml')` to find all `pyproject.toml` files in the repository.
3.  **Identifies Potential Packages**: Each directory containing a `pyproject.toml` is considered a potential package.
4.  **Filters Packages**:
    *   The directory containing the `root_pyproject_path` is excluded from being treated as a sub-package.
    *   Any directories whose relative paths match any of the regex patterns provided in `--ignore-dirs` are excluded.
5.  **Identifies Staged Files**: Uses `git diff --cached --name-only` to find all files staged for commit.
6.  **Detects Changed Packages**: Determines which of the filtered packages have staged changes within their directories.
7.  **Checks for Manual Version Updates**:
    *   For each changed package, it compares the version in its staged `pyproject.toml` (if any) against the version in `HEAD`.
    *   If a package's version was manually changed and staged, the hook acknowledges this and skips auto-bumping for that package.
8.  **Auto-Bumps Patch Version**: If a changed package's version was not manually updated, the hook increments its patch version (e.g., `0.1.0` → `0.1.1`).
9.  **Updates `pyproject.toml`**: Uses `tomlkit` to read the package's `pyproject.toml`, update the version, and write the changes back, preserving existing formatting and comments.
10. **Stages Changes**: Uses `git add` to stage the modified `pyproject.toml` files.
11. **Bumps Root Version (if enabled)**: If any packages were bumped (either automatically or manually acknowledged) and `--dont-bump-root` is not set:
    *   The hook then checks the root `pyproject.toml` (specified by `--root-pyproject-path`).
    *   It performs a similar check for manual updates to the root version.
    *   If not manually updated, it increments the root project's patch version (using `tomlkit`) and stages the change.

If any `pyproject.toml` files are modified by the hook, these changes will be included in the current commit.

## Installation and Usage

1.  **Add this repository to your `.pre-commit-config.yaml`:**

    The hook depends on `tomlkit`, which will be automatically installed by `pre-commit` into the hook's isolated environment due to the `additional_dependencies` setting in this repository's `.pre-commit-hooks.yaml`.

    ```yaml
    repos:
      - repo: https://github.com/rekumar/workspace-version-bump
        rev: v0.1.0  
        hooks:
          - id: version-bump
            args:
              # Optional: Specify regex patterns for directory paths (relative to repo root) to ignore.
              # Directories matching these patterns will not be treated as packages.
              # - "--ignore-dirs"
              # - "^docs/.*"         # Ignore anything under a top-level 'docs' folder
              # - "^tests/fixtures/" # Ignore a specific test fixtures folder
              # - "_cache$"          # Ignore directories ending with '_cache'
              # - "temp_package"     # Ignore any directory named 'temp_package' exactly

              # Optional: Specify the path to your root pyproject.toml
              # Default is "pyproject.toml" (in the repo root)
              # - "--root-pyproject-path"
              # - "my_main_app/pyproject.toml"

              # Optional: Prevent the root pyproject.toml from being version bumped
              # Default is false (meaning root WILL be bumped if sub-packages are)
              # - "--dont-bump-root"
    ```

2.  **Install pre-commit hooks:**

    ```bash
    pre-commit install
    ```

Now, the `version-bump` hook will run automatically each time you commit changes.

## Configuration Arguments

The hook can be configured via the `args` section in your `.pre-commit-config.yaml`:

-   `--ignore-dirs <regex_pattern1> [<regex_pattern2> ...]`
    -   A list of regular expression patterns. Directories containing a `pyproject.toml` whose relative path (from the repository root, using forward slashes) matches any of these patterns will be ignored and not treated as packages for version bumping.
    -   Default: `[]` (empty list)
    -   Examples:
        -   `args: ["--ignore-dirs", "^tests/", ".*/fixtures/.*"]` (ignore top-level `tests` and any `fixtures` subdirectory)
        -   `args: ["--ignore-dirs", "specific_package_name_to_ignore"]` (ignore a directory with this exact name)

-   `--root-pyproject-path <path>`
    -   The path to the root `pyproject.toml` file of your workspace/monorepo.
    -   Default: `"pyproject.toml"` (relative to the repository root)
    -   Example: `args: ["--root-pyproject-path", "./src/my_project/pyproject.toml"]`

-   `--dont-bump-root`
    -   A flag that, if present, prevents the root `pyproject.toml` (specified by `--root-pyproject-path`) from being version bumped, even if sub-packages are bumped.
    -   This is an action flag and does not take a value (e.g. `args: ["--dont-bump-root"]`).
    -   Default: If not specified, the root project will be bumped.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

If you plan to contribute, consider setting up pre-commit for this repository as well:

```bash
# (After cloning the repo)
python -m venv .venv
source .venv/bin/activate
pip install pre-commit tomlkit # Added tomlkit for local dev
pre-commit install
```

## License

This project is licensed under the MIT License - see the `LICENSE` file for details (you may want to add one!). 