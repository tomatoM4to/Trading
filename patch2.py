import sys

file_path = "app/services/screener_service.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

old_window = "PARTITION BY ticker ORDER BY {order_clause} ROWS BETWEEN {w} PRECEDING AND CURRENT ROW"
new_window = "PARTITION BY ticker ORDER BY rn ASC ROWS BETWEEN CURRENT ROW AND {w} FOLLOWING"
content = content.replace(old_window, new_window)

old_lag_short = "LAG({short_line}, 1) OVER(PARTITION BY ticker ORDER BY {order_clause}) as prev_{short_line}"
new_lag_short = "LEAD({short_line}, 1) OVER(PARTITION BY ticker ORDER BY rn ASC) as prev_{short_line}"
content = content.replace(old_lag_short, new_lag_short)

old_lag_long = "LAG({long_line}, 1) OVER(PARTITION BY ticker ORDER BY {order_clause}) as prev_{long_line}"
new_lag_long = "LEAD({long_line}, 1) OVER(PARTITION BY ticker ORDER BY rn ASC) as prev_{long_line}"
content = content.replace(old_lag_long, new_lag_long)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
