import csv
import io
import json
from typing import Any, Dict, List, Optional, Tuple

from django.shortcuts import render

DEFAULT_HIGHLIGHT_LABEL = "自己資産"
RADAR_ITEMS: List[Tuple[str, List[str]]] = [
    ("平均単価:P", ["P", "平均単価"]),
    ("変動単価:V", ["V", "変動単価"]),
    ("売上個数:Q", ["Q", "売上個数"]),
    ("売上高:PQ", ["PQ", "売上高"]),
    ("固定費:F", ["F", "固定費"]),
    ("経常利益:G", ["G", "経常利益"]),
    ("自己資本", ["自己資本"]),
]


def _parse_csv(file_obj) -> Dict[str, Any]:
    """
    Parse the uploaded CSV file and prepare data for the table/chart.
    Returns a dict containing headers, table rows, labels, and datasets.
    """
    decoded_file = file_obj.read().decode("utf-8-sig")
    reader = csv.reader(io.StringIO(decoded_file))
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        raise ValueError("CSVにデータがありません。")

    headers = rows[0]
    if len(headers) < 2:
        raise ValueError("CSVの列が不足しています。")
    periods = headers[1:]
    period_count = len(periods)

    table_rows: List[List[str]] = []
    chart_datasets: List[Dict[str, Any]] = []
    row_lookup: Dict[str, List[Optional[float]]] = {}

    for row in rows[1:]:
        if not row:
            continue
        label = row[0].strip() or "未設定"
        values = row[1:]
        table_rows.append([label, *values])

        numeric_segment = values[-period_count:] if period_count else values
        if len(numeric_segment) < period_count:
            numeric_segment = numeric_segment + [""] * (period_count - len(numeric_segment))

        numeric_values: List[Optional[float]] = []
        has_number = False
        for value in numeric_segment:
            value = value.strip()
            if value == "":
                numeric_values.append(None)
                continue
            try:
                numeric_values.append(float(value))
                has_number = True
            except ValueError:
                numeric_values.append(None)
        if has_number:
            chart_datasets.append(
                {
                    "label": label,
                    "data": numeric_values,
                }
            )
            row_lookup[label] = numeric_values

            metadata_columns = len(values) - period_count
            if metadata_columns > 0:
                descriptors = values[:metadata_columns]
                for descriptor in descriptors:
                    descriptor = descriptor.strip()
                    if descriptor:
                        row_lookup.setdefault(descriptor, numeric_values)

    if not chart_datasets:
        raise ValueError("グラフ化可能な数値データが見つかりませんでした。")

    return {
        "headers": headers,
        "rows": table_rows,
        "periods": periods,
        "datasets": chart_datasets,
        "row_lookup": row_lookup,
    }


def _build_dataset_options(
    datasets: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], str]:
    labels = [dataset.get("label", "") for dataset in datasets]
    highlight_label = DEFAULT_HIGHLIGHT_LABEL
    if highlight_label not in labels and labels:
        highlight_label = labels[0]
    options = [
        {"label": label, "checked": label == highlight_label}
        for label in labels
    ]
    return options, highlight_label


def _build_radar_chart(
    periods: List[str], row_lookup: Dict[str, List[Optional[float]]]
) -> Tuple[List[str], List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not periods:
        return [], [], []
    axis_labels: List[str] = []
    axis_meta: List[Dict[str, Any]] = []
    for axis_label, keys in RADAR_ITEMS:
        axis_labels.append(axis_label)
        values: List[float] = []
        for key in keys:
            if key in row_lookup:
                series = row_lookup[key]
                values = [
                    float(val) if val is not None else 0.0
                    for val in series
                ]
                break
        max_value = max([abs(v) for v in values], default=0.0)
        axis_meta.append(
            {
                "label": axis_label,
                "max_value": max_value if max_value else 1.0,
            }
        )

    radar_datasets: List[Dict[str, Any]] = []
    for period_index, period in enumerate(periods):
        normalized_values: List[float] = []
        original_values: List[float] = []
        for axis_index, (_, keys) in enumerate(RADAR_ITEMS):
            series_values: Optional[List[Optional[float]]] = None
            for key in keys:
                if key in row_lookup:
                    series_values = row_lookup[key]
                    break
            value: float = 0.0
            if series_values and period_index < len(series_values):
                entry = series_values[period_index]
                if entry is not None:
                    value = float(entry)
            original_values.append(value)
            max_value = axis_meta[axis_index]["max_value"]
            normalized = (value / max_value) * 100 if max_value else 0.0
            normalized_values.append(normalized)
        radar_datasets.append(
            {"label": period, "data": normalized_values, "originalData": original_values}
        )
    return axis_labels, radar_datasets, axis_meta


def dashboard(request):
    context: Dict[str, Any] = {
        "table_headers": [],
        "table_rows": [],
        "chart_labels_json": json.dumps([]),
        "chart_datasets_json": json.dumps([]),
        "error": "",
        "dataset_options": [],
        "default_highlight_label": DEFAULT_HIGHLIGHT_LABEL,
        "radar_labels_json": json.dumps([]),
        "radar_datasets_json": json.dumps([]),
        "radar_axis_info_json": json.dumps([]),
        "radar_axis_info": [],
    }

    if request.method == "POST" and request.FILES.get("grades_file"):
        try:
            parsed = _parse_csv(request.FILES["grades_file"])
            options, highlight_label = _build_dataset_options(parsed["datasets"])
            radar_labels, radar_datasets, radar_axis_info = _build_radar_chart(
                parsed["periods"], parsed.get("row_lookup", {})
            )
            context.update(
                {
                    "table_headers": parsed["headers"],
                    "table_rows": parsed["rows"],
                    "chart_labels_json": json.dumps(parsed["periods"]),
                    "chart_datasets_json": json.dumps(parsed["datasets"]),
                    "dataset_options": options,
                    "default_highlight_label": highlight_label,
                    "radar_labels_json": json.dumps(radar_labels),
                    "radar_datasets_json": json.dumps(radar_datasets),
                    "radar_axis_info_json": json.dumps(radar_axis_info),
                    "radar_axis_info": radar_axis_info,
                }
            )
        except ValueError as exc:
            context["error"] = str(exc)
    elif request.method == "POST":
        context["error"] = "CSVファイルを選択してください。"

    return render(request, "App/dashboard.html", context)
