import math

pts = [[0, 0, 0], [10, 0, 0], [20, 0, 0], [30, 0, 0]]
cum_dists = [0.0]
for i in range(len(pts) - 1):
    d = math.hypot(pts[i+1][0] - pts[i][0], pts[i+1][2] - pts[i][2])
    cum_dists.append(cum_dists[-1] + d)

print("Cumulative distances:", cum_dists)

v_dist = 0.0
speed = 10.0
dt = 0.1

trajectory = []
for step in range(35):
    v_dist += speed * dt
    if v_dist >= cum_dists[-1]:
        print(f"Vehicle completed route at step {step}")
        break
    # Find segment
    seg_idx = 0
    while seg_idx < len(cum_dists) - 2 and v_dist >= cum_dists[seg_idx + 1]:
        seg_idx += 1
    d0 = cum_dists[seg_idx]
    d1 = cum_dists[seg_idx + 1]
    frac = (v_dist - d0) / (d1 - d0)
    p0 = pts[seg_idx]
    p1 = pts[seg_idx + 1]
    x = p0[0] + (p1[0] - p0[0]) * frac
    z = p0[2] + (p1[2] - p0[2]) * frac
    trajectory.append((step, seg_idx, round(frac, 2), round(x, 2)))

for t in trajectory:
    print(f"Step {t[0]:02d}: seg_idx={t[1]}, frac={t[2]}, x={t[3]}")

