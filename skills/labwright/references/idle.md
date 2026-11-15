# Idle, busy and down

`lw.py status` marks each host:

- **down**: no service answered within the timeout. A down host is never idle. Say so; do not fall back to another host silently.
- **busy**: any of: ComfyUI queue has running or pending items; Ollama has a loaded model (`/api/ps`; it holds memory a render needs when the card is shared); local GPU load at or above `idle.gpu_busy_pct`. An empty queue is not a free GPU: training runs and scripts outside ComfyUI show only in GPU load.
- **idle**: none of the above.

VRAM held at low load (cached weights) does not count as busy: the host stays idle and status says "X of Y GB VRAM held"; `pick --vram N` adds a note when less than N GB is free now, so free the weights through the API or pick a lighter model before a big job. For unattended starts, read idle on two checks in a row.

On busy: queue behind it and wait with a background loop that parses the queue JSON, also matches failure and has a deadline (quirkwright `qw.py wait`). Never cancel, interrupt, free or restart another session's work. With several idle hosts and a batch, split it across all of them (`pick --batch`).
