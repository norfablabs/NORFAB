# Branch deployment smoke test

Create one tenant and its site using the name supplied by the test.

```yaml context.description
Created from a Markdown design.
```

```yaml design
tenants:
  - name: "{{ context.name }}"
    description: "{{ context.description }}"
```

```yaml design
sites:
  - name: "{{ context.name }}"
    tenant: "{{ context.name }}"
    description: "{{ context.description }}"
```
