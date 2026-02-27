"""
Nemo 매물 데이터 대시보드 (Advanced Version)
실행 방법:
1. 가상환경 설치 (uv venv)
2. 필수 패키지 설치: pip install streamlit pandas plotly
3. 실행: streamlit run nemo/app.py
"""

import streamlit as st
import pandas as pd
import json
import os
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import html

# --- 페이지 설정 ---
st.set_page_config(page_title="Nemo Advanced Dashboard", layout="wide")

# --- 유틸리티 및 전처리 함수 ---
@st.cache_data
def load_and_preprocess_data(filename="sample_data.json"):
    # 1. 파일 경로 후보 확인 (배포 시 루트, 로컬 시 nemo/ 폴더 아래)
    paths = [
        filename,                   # Root (GitHub 배포 시)
        os.path.join("nemo", filename)  # nemo/ 폴더 아래 (로컬 작업 시)
    ]
    
    file_path = None
    for p in paths:
        if os.path.exists(p):
            file_path = p
            break
            
    if file_path is None:
        return pd.DataFrame()
    
    with open(file_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    
    # 리스트 또는 단일 객체 처리
    if isinstance(raw_data, dict):
        df = pd.DataFrame([raw_data])
    else:
        df = pd.DataFrame(raw_data)
    
    # 1) 타입 변환 및 결측치 처리
    numeric_cols = ['monthlyRent', 'deposit', 'premium', 'maintenanceFee', 'size', 'floor', 'groundFloor', 'viewCount', 'favoriteCount']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # 2) 시간 변환 (KST 변환: UTC+9)
    def to_kst(utc_str):
        try:
            if not isinstance(utc_str, str): return utc_str
            dt = datetime.fromisoformat(utc_str.replace('Z', '+00:00'))
            kst = dt + timedelta(hours=9)
            return kst.strftime('%Y-%m-%d %H:%M:%S')
        except:
            return utc_str
            
    if 'editedDateUtc' in df.columns:
        df['edited_kst'] = df['editedDateUtc'].apply(to_kst)
    
    # 3) 실질 비용 및 평수 계산 (기본 m2 기준)
    df['total_monthly_cost'] = df['monthlyRent'].fillna(0) + df['maintenanceFee'].fillna(0)
    df['size_pyeong'] = df['size'] / 3.3058
    
    return df

# --- 화면 구성 ---
def main():
    st.title("🏙️ Nemo 매물 분석 대시보드 (EDA)")
    
    # 데이터 로드 (자동 경로 탐색)
    df = load_and_preprocess_data("sample_data.json")
    
    if df.empty:
        st.error("데이터 소스(nemo/sample_data.json)를 찾을 수 없거나 비어 있습니다.")
        if st.button("필터 초기화"):
            st.rerun()
        return

    # --- 사이드바: 단위 및 검색 필터 ---
    st.sidebar.header("⚙️ 대시보드 설정")
    use_raw_won = st.sidebar.checkbox("금액을 '원' 단위로 표시 (x10,000)")
    use_pyeong = st.sidebar.checkbox("면적을 '평' 단위로 표시")
    
    st.sidebar.markdown("---")
    st.sidebar.header("🔍 필터링")
    
    # 카테고리 필터
    all_cats = sorted(df['businessMiddleCodeName'].dropna().unique())
    selected_cats = st.sidebar.multiselect("업종 선택", all_cats, default=all_cats)
    
    # 가격 슬라이더 (만원 단위)
    def slider_filter(label, col, key):
        min_v = int(df[col].min()) if not pd.isna(df[col].min()) else 0
        max_v = int(df[col].max()) if not pd.isna(df[col].max()) else 1000
        return st.sidebar.slider(label, min_v, max_v, (min_v, max_v), key=key)

    rent_range = slider_filter("월세 범위(만원)", "monthlyRent", "rent")
    deposit_range = slider_filter("보증금 범위(만원)", "deposit", "depo")
    premium_range = slider_filter("권리금 범위(만원)", "premium", "prem")
    size_range = slider_filter("전용면적(m2)", "size", "size_sl")
    
    # 검색
    subway_search = st.sidebar.text_input("지하철역 검색")
    title_search = st.sidebar.text_input("제목 검색")
    
    # 인기 매물 필터
    st.sidebar.subheader("🔥 인기/추천 필터")
    view_threshold = st.sidebar.slider("조회수 기준 (이상)", 0, int(df['viewCount'].max() or 0), 0)
    fav_threshold = st.sidebar.slider("즐겨찾기 기준 (이상)", 0, int(df['favoriteCount'].max() or 0), 0)

    # --- 데이터 필터링 적용 ---
    mask = (
        df['businessMiddleCodeName'].isin(selected_cats) &
        df['monthlyRent'].between(*rent_range) &
        df['deposit'].between(*deposit_range) &
        df['premium'].between(*premium_range) &
        df['size'].between(*size_range) &
        (df['viewCount'] >= view_threshold) &
        (df['favoriteCount'] >= fav_threshold)
    )
    
    if subway_search:
        mask &= df['nearSubwayStation'].str.contains(subway_search, na=False, case=False)
    if title_search:
        mask &= df['title'].str.contains(title_search, na=False, case=False)
        
    filtered_df = df[mask]

    # --- KPI 섹션 ---
    st.subheader("📊 주요 지표 (KPI)")
    if not filtered_df.empty:
        c1, c2, c3, c4, c5 = st.columns(5)
        
        def display_val(val, is_money=True):
            if pd.isna(val): return "-"
            if is_money:
                return f"{int(val * 10000):,}원" if use_raw_won else f"{int(val):,}만원"
            return f"{val:,.1f}"

        c1.metric("매물 수", f"{len(filtered_df)} 건")
        c2.metric("평균 월세", display_val(filtered_df['monthlyRent'].mean()))
        c3.metric("평균 보증금", display_val(filtered_df['deposit'].mean()))
        c4.metric("평균 실질비용", display_val(filtered_df['total_monthly_cost'].mean()))
        
        avg_size = filtered_df['size'].mean()
        size_label = f"{avg_size/3.3058:.1f}평" if use_pyeong else f"{avg_size:.1f}m2"
        c5.metric("평균 면적", size_label)
        
        c1b, c2b, c3b, c4b, c5b = st.columns(5)
        c1b.metric("중앙 월세", display_val(filtered_df['monthlyRent'].median()))
        c2b.metric("평균 권리금", display_val(filtered_df['premium'].mean()))
        c3b.metric("평균 관리비", display_val(filtered_df['maintenanceFee'].mean()))
        c4b.metric("총 조회수", f"{int(filtered_df['viewCount'].sum()):,}회")
        c5b.metric("총 즐겨찾기", f"{int(filtered_df['favoriteCount'].sum()):,}개")
    else:
        st.warning("필터 조건에 맞는 매물이 없습니다.")

    # --- 차트 섹션 ---
    st.markdown("---")
    st.subheader("📈 데이터 시각화 (EDA)")
    
    if not filtered_df.empty:
        row1_col1, row1_col2 = st.columns(2)
        
        with row1_col1:
            st.write("### 업종별 매물 분포")
            # Pandas 버전에 관계없이 동작하도록 컬럼명 명시적 지정
            counts_df = filtered_df['businessMiddleCodeName'].value_counts().reset_index()
            counts_df.columns = ['업종', '수']
            fig1 = px.bar(counts_df, x='업종', y='수', color='업종')
            st.plotly_chart(fig1, use_container_width=True)
            
        with row1_col2:
            st.write("### 월세 가격대 분포 (만원)")
            fig2 = px.histogram(filtered_df, x="monthlyRent", nbins=20, color_discrete_sequence=['#19589d'])
            st.plotly_chart(fig2, use_container_width=True)
            
        row2_col1, row2_col2 = st.columns(2)
        
        with row2_col1:
            st.write("### 보증금 vs 월세 상관관계")
            # 보증금이 너무 크면 로그 스케일 고려 가능하나 여기선 일반 산점도
            fig3 = px.scatter(filtered_df, x="deposit", y="monthlyRent", 
                              color="businessMiddleCodeName", size="favoriteCount",
                              hover_data=['title'], template="plotly_white")
            st.plotly_chart(fig3, use_container_width=True)
            
        with row2_col2:
            st.write("### 면적 vs 월세 상관관계")
            x_col = "size_pyeong" if use_pyeong else "size"
            x_label = "면적 (평)" if use_pyeong else "면적 (m2)"
            fig4 = px.scatter(filtered_df, x=x_col, y="monthlyRent", 
                              color="businessMiddleCodeName", hover_data=['title'],
                              labels={x_col: x_label, "monthlyRent": "월세 (만원)"})
            st.plotly_chart(fig4, use_container_width=True)

    # --- 데이터 테이블 섹션 ---
    st.markdown("---")
    st.subheader("📋 매물 상세 리스트")
    
    if not filtered_df.empty:
        # 정렬 옵션
        sort_col = st.selectbox("정렬 기준", ["수정일 최신순", "월세 낮은순", "보증금 낮은순", "조회수 많은순", "실질비용 낮은순"])
        sort_map = {
            "수정일 최신순": ("editedDateUtc", False),
            "월세 낮은순": ("monthlyRent", True),
            "보증금 낮은순": ("deposit", True),
            "조회수 많은순": ("viewCount", False),
            "실질비용 낮은순": ("total_monthly_cost", True)
        }
        s_col, s_asc = sort_map[sort_col]
        display_df = filtered_df.sort_values(by=s_col, ascending=s_asc)
        
        # 테이블 표시 루프
        for idx, row in display_df.iterrows():
            with st.expander(f"[{row['businessMiddleCodeName']}] {row['title']} | {display_val(row['monthlyRent'])} / {display_val(row['deposit'])}"):
                c_img, c_txt = st.columns([1, 2])
                
                with c_img:
                    if row['previewPhotoUrl']:
                        st.image(row['previewPhotoUrl'], use_column_width=True)
                    else:
                        st.write("이미지 없음")
                
                with c_txt:
                    # 정보 요약
                    st.write(f"**상세 제목:** {row['title']}")
                    st.write(f"**위치:** {row['nearSubwayStation']}")
                    st.write(f"**면적:** {row['size']:.1f} m2 ({row['size_pyeong']:.1f} 평) | **층수:** {row['floor']} / {row['groundFloor']}층")
                    
                    # 가격 상세 내역
                    st.markdown("#### 💰 가격 상세")
                    p_col1, p_col2 = st.columns(2)
                    p_col1.write(f"**보증금:** {display_val(row['deposit'])}")
                    p_col1.write(f"**월세:** {display_val(row['monthlyRent'])}")
                    p_col2.write(f"**권리금:** {display_val(row['premium'])}")
                    p_col2.write(f"**관리비:** {display_val(row['maintenanceFee'])}")
                    st.info(f"**실질 월 비용 (월세+관리비):** {display_val(row['total_monthly_cost'])}")
                    
                    st.write(f"**조회수:** {row['viewCount']} | **즐겨찾기:** {row['favoriteCount']}")
                    st.write(f"*수정일(KST): {row['edited_kst']}*")

if __name__ == "__main__":
    main()
