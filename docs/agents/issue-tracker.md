# Issue tracker: Local markdown

Issues and PRDs for this repo live as markdown files under `.scratch/<feature>/` in this repo.

## Conventions

- **Create an issue**: Write a markdown file under `.scratch/<feature>/` with frontmatter `status`, `title`, and `created`.
- **Read an issue**: Read the markdown file directly.
- **List issues**: Use `glob` to find files under `.scratch/`.
- **Update status**: Edit the frontmatter `status` field.

## File structure

```
.scratch/
└── feature-name/
    └── 0001-issue-title.md
```

## When a skill says "publish to the issue tracker"

Create a new markdown file under `.scratch/<feature>/`.

## When a skill says "fetch the relevant ticket"

Read the markdown file from `.scratch/<feature>/`.
