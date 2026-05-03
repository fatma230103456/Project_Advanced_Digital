"""Build interactive forensic maps with Folium."""
from __future__ import annotations

import base64
import html as html_lib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import folium
from folium.plugins import HeatMap, MarkerCluster, AntPath

from ..core.exif_extractor import ExifData
from ..core.correlator import build_timeline


SEVERITY_COLOR = {
    "critical": "darkred",
    "high": "red",
    "medium": "orange",
    "low": "blue",
    "info": "lightgray",
    None: "green",
}


@dataclass
class MapPoint:
    latitude: float
    longitude: float
    label: str
    timestamp: Optional[str] = None
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    camera: Optional[str] = None
    severity: Optional[str] = None
    thumbnail_b64: Optional[str] = None


class MapBuilder:
    """Generate self-contained HTML maps from a list of evidence items."""

    DEFAULT_TILES = "OpenStreetMap"
    EGYPT_CENTER = (26.8206, 30.8025)
    DEFAULT_ZOOM = 5

    def __init__(self, tiles: str = DEFAULT_TILES):
        self.tiles = tiles

    def build(
        self,
        items: Iterable[ExifData],
        anomaly_index: Optional[dict[str, str]] = None,
        show_path: bool = True,
        show_heatmap: bool = True,
        show_clusters: bool = True,
        animate_path: bool = True,
    ) -> folium.Map:
        anomaly_index = anomaly_index or {}
        points = self._items_to_points(items, anomaly_index)
        center, zoom = self._compute_view(points)
        fmap = folium.Map(location=center, zoom_start=zoom, tiles=self.tiles, control_scale=True)
        if not points:
            folium.Marker(
                location=center,
                tooltip="No GPS-tagged images in case",
                icon=folium.Icon(color="gray", icon="info-sign"),
            ).add_to(fmap)
            return fmap
        marker_target = MarkerCluster(name="Evidence").add_to(fmap) if show_clusters else fmap
        for p in points:
            folium.Marker(
                location=(p.latitude, p.longitude),
                tooltip=p.label,
                popup=folium.Popup(self._popup_html(p), max_width=400),
                icon=folium.Icon(
                    color=SEVERITY_COLOR.get(p.severity, "blue"),
                    icon="camera", prefix="fa",
                ),
            ).add_to(marker_target)
        if show_path and len(points) > 1:
            sorted_pts = sorted(points, key=lambda x: x.timestamp or "")
            coords = [(p.latitude, p.longitude) for p in sorted_pts]
            if animate_path:
                AntPath(coords, color="#1e88e5", weight=3, dash_array=[10, 20]).add_to(fmap)
            else:
                folium.PolyLine(coords, color="#1e88e5", weight=3, opacity=0.7).add_to(fmap)
            for idx, p in enumerate(sorted_pts, start=1):
                folium.map.Marker(
                    location=(p.latitude, p.longitude),
                    icon=folium.DivIcon(
                        icon_size=(28, 28), icon_anchor=(14, 14),
                        html=(
                            f'<div style="font-size:11px;font-weight:bold;color:white;'
                            f'background:#222;border:2px solid #fff;border-radius:50%;'
                            f'width:24px;height:24px;text-align:center;line-height:20px;">{idx}</div>'
                        ),
                    ),
                ).add_to(fmap)
        if show_heatmap and len(points) > 2:
            HeatMap(
                [(p.latitude, p.longitude, 0.6) for p in points],
                radius=25, blur=20, name="Density",
                show=False,
            ).add_to(fmap)
        folium.LayerControl(collapsed=False).add_to(fmap)
        self._add_legend(fmap)
        return fmap

    def save(self, fmap: folium.Map, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fmap.save(str(out))
        return out

    def render(self, fmap: folium.Map) -> str:
        return fmap.get_root().render()

    # ---------- helpers ----------

    @staticmethod
    def _items_to_points(items, anomaly_index) -> list[MapPoint]:
        timeline = build_timeline(items)
        points: list[MapPoint] = []
        for entry in timeline:
            if entry.gps is None:
                continue
            severity = anomaly_index.get(entry.file_path)
            thumb_b64 = None
            for d in items:
                if d.file_path == entry.file_path and d.thumbnail_bytes:
                    thumb_b64 = base64.b64encode(d.thumbnail_bytes).decode("ascii")
                    break
            points.append(MapPoint(
                latitude=entry.gps.latitude,
                longitude=entry.gps.longitude,
                label=entry.file_name,
                timestamp=entry.timestamp.isoformat() if entry.timestamp else None,
                file_path=entry.file_path,
                file_name=entry.file_name,
                camera=entry.camera,
                severity=severity,
                thumbnail_b64=thumb_b64,
            ))
        return points


    @classmethod
    def _compute_view(cls, points: list[MapPoint]) -> tuple[tuple[float, float], int]:
        if not points:
            return cls.EGYPT_CENTER, cls.DEFAULT_ZOOM
        lats = [p.latitude for p in points]
        lons = [p.longitude for p in points]
        center = (sum(lats) / len(lats), sum(lons) / len(lons))
        span = max(max(lats) - min(lats), max(lons) - min(lons))
        if span < 0.01:
            zoom = 16
        elif span < 0.1:
            zoom = 13
        elif span < 1.0:
            zoom = 10
        elif span < 10.0:
            zoom = 7
        elif span < 50.0:
            zoom = 5
        else:
            zoom = 3
        return center, zoom

    @staticmethod
    def _popup_html(p: MapPoint) -> str:
        rows = [
            ("File", p.file_name),
            ("Time", p.timestamp),
            ("Camera", p.camera),
            ("Latitude", f"{p.latitude:.6f}"),
            ("Longitude", f"{p.longitude:.6f}"),
        ]
        if p.severity:
            rows.append(("Anomaly", p.severity.upper()))
        body = "".join(
            f"<tr><th style='text-align:left;padding:2px 6px;color:#555'>"
            f"{html_lib.escape(str(k))}</th>"
            f"<td style='padding:2px 6px'>{html_lib.escape(str(v) if v is not None else '-')}</td></tr>"
            for k, v in rows
        )
        thumb_html = ""
        if p.thumbnail_b64:
            thumb_html = (
                f"<img src='data:image/jpeg;base64,{p.thumbnail_b64}' "
                f"style='max-width:280px;max-height:200px;display:block;"
                f"margin:6px auto;border:1px solid #ddd;border-radius:4px;'/>"
            )
        return (
            f"<div style='font-family:Segoe UI,Arial,sans-serif;font-size:12px;'>"
            f"{thumb_html}<table style='border-collapse:collapse'>{body}</table></div>"
        )

    @staticmethod
    def _add_legend(fmap: folium.Map) -> None:
        legend = """
        <div style="position: fixed; bottom: 20px; left: 20px; z-index: 9999;
                    background: rgba(255,255,255,0.92); padding: 8px 12px;
                    border: 1px solid #888; border-radius: 6px;
                    font: 12px Segoe UI, Arial; box-shadow: 0 2px 6px rgba(0,0,0,0.2);">
          <strong>Anomaly Severity</strong><br/>
          <span style="display:inline-block;width:10px;height:10px;background:darkred;border-radius:50%"></span> Critical &nbsp;
          <span style="display:inline-block;width:10px;height:10px;background:red;border-radius:50%"></span> High<br/>
          <span style="display:inline-block;width:10px;height:10px;background:orange;border-radius:50%"></span> Medium &nbsp;
          <span style="display:inline-block;width:10px;height:10px;background:blue;border-radius:50%"></span> Low<br/>
          <span style="display:inline-block;width:10px;height:10px;background:green;border-radius:50%"></span> No issue
        </div>
        """
        fmap.get_root().html.add_child(folium.Element(legend))
