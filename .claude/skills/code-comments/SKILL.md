---
name: code-comments
description: House style for comments and docstrings in this repo. Use whenever writing, editing or reviewing Python functions here (e.g. code/sigproc/ft8). Every function gets one docstring with at most a one-sentence summary, its inputs with types, and its return value with type; nothing more.
---

# Commenting style

Every function and method gets a docstring with **at most** these three parts, in this order:

1. **One sentence** saying what the function does.
2. **Args:** each input on one line, as `name (type): what it is`.
3. **Returns:** one line, as `type: what it is`.

```python
def tone_bins(self, t_idx: int, f_idx: int) -> np.ndarray:
    """
    Read the 8 FT8 tone powers of one symbol from the waterfall.

    Args:
        t_idx (int): row of the symbol
        f_idx (int): column of tone 0

    Returns:
        np.ndarray: shape [8], linear power of tones 0-7
    """
```

## Rules
- **One sentence is the maximum.** No second paragraph, background, derivation, or notes.
  If something needs more, it belongs in the commit message or the docs, not the docstring.
- **List every input with its type.** Skip `self`. Include shapes and units where they
  matter, e.g. `np.ndarray: shape [58, 8]`, `float: Hz`.
- **Omit sections that don't apply.** No `Args:` if there are no inputs other than `self`.
  No `Returns:` if the function returns `None`.
- **Keep the Python type hints in the signature** as well.
- **Inline comments are rare.** Add one only where a line would otherwise be wrong-looking or
  surprising, kept to a short phrase. Don't restate what the code does.
- **Module docstrings and constants** get one short line each, at most.
- When editing an existing function, bring its docstring into this format.
