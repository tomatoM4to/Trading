import logging
from pathlib import Path

import pandas as pd
from core.database import connect_sqlite

# scripts 디렉토리 모듈 임포트
from scripts.kis_kosdaq_code_mst import (
    get_kosdaq_master_dataframe,
    kosdaq_master_download,
)
from scripts.kis_kospi_code_mst import get_kospi_master_dataframe, kospi_master_download

logger = logging.getLogger(__name__)


def init_stock_codes_db():
    """코스피, 코스닥 종목 마스터 파일을 다운로드하여 CSV로 저장한 뒤 파싱하여 SQLite DB에 저장한다."""
    # 다운로드 및 파일 생성 디렉토리 (app/data)
    base_dir = Path(__file__).resolve().parent.parent / "data"
    base_dir.mkdir(parents=True, exist_ok=True)
    base_dir_str = str(base_dir)

    kospi_csv_path = base_dir / "kospi_codes.csv"
    kosdaq_csv_path = base_dir / "kosdaq_codes.csv"

    logger.info("Downloading and processing KOSPI master file...")
    kospi_master_download(base_dir_str)
    kospi_df = get_kospi_master_dataframe(base_dir_str)
    kospi_df["market"] = "KOSPI"
    # 데이터프레임을 CSV 파일로 먼저 생성 (엑셀/한글 호환성을 위해 utf-8-sig 사용)
    kospi_df.to_csv(kospi_csv_path, index=False, encoding="utf-8-sig")
    logger.info("Created CSV file: %s", kospi_csv_path.name)

    logger.info("Downloading and processing KOSDAQ master file...")
    kosdaq_master_download(base_dir_str)
    kosdaq_df = get_kosdaq_master_dataframe(base_dir_str)
    kosdaq_df["market"] = "KOSDAQ"
    # 데이터프레임을 CSV 파일로 먼저 생성
    kosdaq_df.to_csv(kosdaq_csv_path, index=False, encoding="utf-8-sig")
    logger.info("Created CSV file: %s", kosdaq_csv_path.name)

    logger.info("Parsing CSV files and combining with filters...")
    # 만들어진 CSV 파일을 다시 파싱해서 읽기
    parsed_kospi_df = pd.read_csv(kospi_csv_path, dtype=str)
    parsed_kosdaq_df = pd.read_csv(kosdaq_csv_path, dtype=str)

    # 1. KOSPI 필터링
    kpi = parsed_kospi_df
    kpi = kpi[
        kpi["그룹코드"].str.strip() == "ST"
    ]  # 보통주(주식)만 남김 (펀드, ETF, ETN, 리츠 등 완벽 제거)
    kpi = kpi[kpi["거래정지"].str.strip() != "Y"]
    kpi = kpi[kpi["정리매매"].str.strip() != "Y"]
    kpi = kpi[kpi["관리종목"].str.strip() != "Y"]
    kpi = kpi[kpi["SPAC"].str.strip() != "Y"]
    kpi = kpi[kpi["우선주"].str.strip() == "0"]
    kpi = kpi[kpi["단기과열"].str.strip() == "0"]
    kpi = kpi[kpi["저유동성"].str.strip() != "Y"]

    kpi_cols = {
        "단축코드": "ticker",
        "한글명": "name",
        "market": "market",
        "시가총액": "market_cap",
        "상장주수": "total_shares",
        "신용가능": "credit_able",
        "증거금비율": "margin_rate",
    }
    kpi = kpi[list(kpi_cols.keys())].rename(columns=kpi_cols)

    # 2. KOSDAQ 필터링
    kdq = parsed_kosdaq_df
    kdq = kdq[kdq["증권그룹구분코드"].str.strip() == "ST"]  # 보통주(주식)만 남김
    kdq = kdq[kdq["거래정지 여부"].str.strip() != "Y"]
    kdq = kdq[kdq["정리매매 여부"].str.strip() != "Y"]
    kdq = kdq[kdq["관리 종목 여부"].str.strip() != "Y"]
    kdq = kdq[kdq["기업인수목적회사여부"].str.strip() != "Y"]
    kdq = kdq[kdq["우선주 구분 코드"].str.strip() == "0"]
    kdq = kdq[kdq["단기과열종목구분코드"].str.strip() == "0"]
    kdq = kdq[kdq["저유동성종목 여부"].str.strip() != "Y"]
    kdq = kdq[kdq["(코스닥)투자주의환기종목여부"].str.strip() != "Y"]

    kdq_cols = {
        "단축코드": "ticker",
        "한글종목명": "name",
        "market": "market",
        "전일기준 시가총액 (억)": "market_cap",
        "상장 주수(천)": "total_shares",
        "신용주문 가능 여부": "credit_able",
        "증거금 비율": "margin_rate",
    }
    kdq = kdq[list(kdq_cols.keys())].rename(columns=kdq_cols)

    combined_df = pd.concat([kpi, kdq], ignore_index=True)

    # 숫자형 데이터 변환
    numeric_cols = ["market_cap", "total_shares", "margin_rate"]
    for col in numeric_cols:
        combined_df[col] = pd.to_numeric(combined_df[col], errors="coerce").fillna(0)

    logger.info("Saving parsed stock codes to SQLite database...")
    conn = connect_sqlite()
    try:
        combined_df.to_sql("stock_codes", conn, if_exists="replace", index=False)
        logger.info(
            f"Successfully initialized {len(combined_df)} stock codes into database from CSV."
        )
    except Exception as e:
        logger.error("Failed to save stock codes to database: %s", e)
        raise e
    finally:
        conn.close()

    # 파싱 후 남은 임시 파일 정리
    cleanup_temp_files(base_dir)


def cleanup_temp_files(base_dir: Path):
    """파싱 이후 남은 임시 마스터 파일(.mst, .zip, .tmp)을 삭제한다."""
    logger.info("Cleaning up temporary master files...")
    for ext in ["*.mst", "*.zip", "*.tmp"]:
        for file_path in base_dir.glob(ext):
            try:
                file_path.unlink()
            except Exception as e:
                logger.warning("Could not delete temp file %s: %s", file_path.name, e)
