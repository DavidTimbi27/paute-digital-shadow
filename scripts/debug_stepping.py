import math

pts = [[0, 0, 0], [10, 0, 0], [20, 0, 0], [30, 0, 0]]
v = {
    "points": pts,
    "seg_idx": 0,
    "seg_t": 0.0,
    "speed": 10.0,
    "x": 0.0,
    "z": 0.0
}

dt = 0.1 # 100ms
trajectory = []

for step in range(40):
    idx = v["seg_idx"]
    if idx >= len(pts) - 1:
        print(f"Vehicle FINISHED at step {step}")
        break
    p1 = pts[idx]
    p2 = pts[idx + 1]
    dx = p2[0] - p1[0]
    dz = p2[2] - p1[2]
    dist = math.hypot(dx, dz)
    delta_t = (v["speed"] * dt) / dist
    v["seg_t"] += delta_t
    if v["seg_t"] >= 1.0:
        v["seg_idx"] += 1
        v["seg_t"] = 0.0
        if v["seg_idx"] >= len(pts) - 1:
            print(f"Vehicle FINISHED inside seg_t check at step {step}")
            break
    t = v["seg_t"]
    v["x"] = p1[0] + dx * t
    v["z"] = p1[2] + dz * t
    trajectory.append((step, v["seg_idx"], round(v["seg_t"], 2), round(v["x"], 2)))

for t in trajectory[:25]:
    print(f"Step {t[0]:02d}: seg_idx={t[1]}, seg_t={t[2]}, x={t[3]}")

