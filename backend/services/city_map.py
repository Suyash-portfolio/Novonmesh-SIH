import json
import os
import math
import heapq

_map_data = None
_adjacency = None


def _load_map():
    global _map_data, _adjacency
    if _map_data is not None:
        return _map_data

    base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "map")

    with open(os.path.join(base, "nodes.json")) as f:
        nodes_data = json.load(f)
    with open(os.path.join(base, "roads.json")) as f:
        roads_data = json.load(f)
    with open(os.path.join(base, "cameras.json")) as f:
        cameras_data = json.load(f)
    with open(os.path.join(base, "zones.json")) as f:
        zones_data = json.load(f)

    nodes = {n["id"]: n for n in nodes_data["nodes"]}
    roads = {r["id"]: r for r in roads_data["roads"]}
    cameras = {c["id"]: c for c in cameras_data["cameras"]}

    adjacency = {}
    for nid in nodes:
        adjacency[nid] = []

    for road in roads_data["roads"]:
        fid = road["from"]
        tid = road["to"]
        n1 = nodes[fid]
        n2 = nodes[tid]
        dx = n2["x"] - n1["x"]
        dy = n2["y"] - n1["y"]
        dist = math.sqrt(dx * dx + dy * dy)

        weight = dist / (road.get("speedLimit", 40) or 40)

        adjacency[fid].append({"node": tid, "road": road["id"], "dist": dist, "weight": weight})
        if road.get("direction", "both") == "both":
            adjacency[tid].append({"node": fid, "road": road["id"], "dist": dist, "weight": weight})

    _map_data = {
        "nodes": nodes,
        "roads": roads,
        "cameras": cameras,
        "zones": zones_data.get("zones", []),
    }
    _adjacency = adjacency
    return _map_data


def find_path(start_camera_id, end_camera_id):
    data = _load_map()
    nodes = data["nodes"]
    cameras = data["cameras"]

    start_cam = cameras.get(start_camera_id)
    end_cam = cameras.get(end_camera_id)
    if not start_cam or not end_cam:
        return None

    start_node = start_cam["nodeId"]
    end_node = end_cam["nodeId"]

    if start_node == end_node:
        return {
            "path": [start_node],
            "roads": [],
            "distance": 0,
            "estimatedTime": 0,
            "geometry": [{"x": start_cam["x"], "y": start_cam["y"]}],
        }

    dist = {nid: float("inf") for nid in nodes}
    prev = {nid: None for nid in nodes}
    prev_road = {nid: None for nid in nodes}
    dist[start_node] = 0
    pq = [(0, start_node)]

    while pq:
        d, u = heapq.heappop(pq)
        if d > dist[u]:
            continue
        if u == end_node:
            break
        for edge in _adjacency.get(u, []):
            v = edge["node"]
            new_dist = d + edge["weight"]
            if new_dist < dist[v]:
                dist[v] = new_dist
                prev[v] = u
                prev_road[v] = edge["road"]
                heapq.heappush(pq, (new_dist, v))

    if prev[end_node] is None and start_node != end_node:
        return None

    path_nodes = []
    path_roads = []
    current = end_node
    while current is not None:
        path_nodes.append(current)
        if prev_road[current] is not None:
            path_roads.append(prev_road[current])
        current = prev[current]

    path_nodes.reverse()
    path_roads.reverse()

    geometry = []
    for nid in path_nodes:
        n = nodes[nid]
        geometry.append({"x": n["x"], "y": n["y"], "label": n.get("label", nid)})

    total_dist = dist[end_node] * 10
    est_time = dist[end_node]

    return {
        "path": path_nodes,
        "roads": path_roads,
        "distance": round(total_dist, 1),
        "estimatedTime": round(est_time, 1),
        "geometry": geometry,
    }


def find_all_paths_between_cameras():
    data = _load_map()
    cameras = data["cameras"]
    camera_ids = list(cameras.keys())
    paths = {}
    for i in range(len(camera_ids)):
        for j in range(len(camera_ids)):
            if i == j:
                continue
            c1 = camera_ids[i]
            c2 = camera_ids[j]
            key = f"{c1}->{c2}"
            path = find_path(c1, c2)
            if path:
                paths[key] = path
    return paths


def generate_road_points(path_result, num_points=20):
    if not path_result or not path_result.get("geometry"):
        return []

    geometry = path_result["geometry"]
    if len(geometry) < 2:
        return [{"x": geometry[0]["x"], "y": geometry[0]["y"]}]

    total_length = 0
    segments = []
    for i in range(len(geometry) - 1):
        dx = geometry[i + 1]["x"] - geometry[i]["x"]
        dy = geometry[i + 1]["y"] - geometry[i]["y"]
        seg_len = math.sqrt(dx * dx + dy * dy)
        segments.append(seg_len)
        total_length += seg_len

    points = []
    for i in range(num_points):
        t = i / max(num_points - 1, 1)
        target_dist = t * total_length

        cumulative = 0
        for seg_idx, seg_len in enumerate(segments):
            if cumulative + seg_len >= target_dist - 0.001:
                seg_t = (target_dist - cumulative) / seg_len if seg_len > 0 else 0
                x = geometry[seg_idx]["x"] + seg_t * (geometry[seg_idx + 1]["x"] - geometry[seg_idx]["x"])
                y = geometry[seg_idx]["y"] + seg_t * (geometry[seg_idx + 1]["y"] - geometry[seg_idx]["y"])
                points.append({"x": round(x, 1), "y": round(y, 1)})
                break
            cumulative += seg_len

    if points and len(points) < num_points:
        last = geometry[-1]
        points.append({"x": last["x"], "y": last["y"]})

    return points


def snap_point_to_road(x, y):
    data = _load_map()
    nodes = data["nodes"]
    roads = data["roads"]
    best_dist = float("inf")
    best_point = {"x": x, "y": y}

    for road in data["roads"].values():
        n1 = nodes.get(road["from"])
        n2 = nodes.get(road["to"])
        if not n1 or not n2:
            continue

        px, py = x, y
        ax, ay = n1["x"], n1["y"]
        bx, by = n2["x"], n2["y"]
        abx, aby = bx - ax, by - ay
        apx, apy = px - ax, py - ay

        ab_len_sq = abx * abx + aby * aby
        if ab_len_sq < 0.001:
            continue

        t = max(0, min(1, (apx * abx + apy * aby) / ab_len_sq))
        proj_x = ax + t * abx
        proj_y = ay + t * aby

        d = math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)
        if d < best_dist:
            best_dist = d
            best_point = {"x": round(proj_x, 1), "y": round(proj_y, 1)}

    return best_point


def get_road_network():
    data = _load_map()
    nodes_list = [{"id": n["id"], "x": n["x"], "y": n["y"], "label": n.get("label", "")} for n in data["nodes"].values()]
    roads_list = []
    for r in data["roads"].values():
        n1 = data["nodes"].get(r["from"], {})
        n2 = data["nodes"].get(r["to"], {})
        roads_list.append({
            "id": r["id"],
            "from": r["from"],
            "to": r["to"],
            "name": r.get("name", ""),
            "type": r.get("type", "secondary"),
            "width": r.get("width", 3),
            "direction": r.get("direction", "both"),
            "speedLimit": r.get("speedLimit", 40),
            "geometry": [
                {"x": n1.get("x", 0), "y": n1.get("y", 0)},
                {"x": n2.get("x", 0), "y": n2.get("y", 0)},
            ],
        })
    cameras_list = list(data["cameras"].values())
    zones_list = data.get("zones", [])

    return {
        "nodes": nodes_list,
        "roads": roads_list,
        "cameras": cameras_list,
        "zones": zones_list,
    }


def compute_traffic_flow():
    from backend.extensions import db
    from backend.models.sighting import VehicleSighting
    from sqlalchemy import func

    data = _load_map()
    road_flow = {}

    for road_id, road in data["roads"].items():
        road_flow[road_id] = {
            "id": road_id,
            "name": road.get("name", ""),
            "type": road.get("type", "secondary"),
            "vehicleCount": 0,
            "congestion": "low",
        }

    try:
        camera_flows = db.session.query(
            VehicleSighting.camera_id,
            func.count(VehicleSighting.id).label("count")
        ).group_by(VehicleSighting.camera_id).all()

        for cf in camera_flows:
            cam_id = cf[0]
            count = cf[1]
            cam_info = data["cameras"].get(cam_id)
            if not cam_info:
                continue

            node_id = cam_info["nodeId"]
            for road_id, road in data["roads"].items():
                if road["from"] == node_id or road["to"] == node_id:
                    road_flow[road_id]["vehicleCount"] += count

        for rf in road_flow.values():
            vc = rf["vehicleCount"]
            if vc > 200:
                rf["congestion"] = "severe"
            elif vc > 100:
                rf["congestion"] = "high"
            elif vc > 30:
                rf["congestion"] = "moderate"
            else:
                rf["congestion"] = "low"

    except Exception:
        pass

    return list(road_flow.values())
