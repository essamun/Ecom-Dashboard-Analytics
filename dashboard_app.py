import pandas as pd
import streamlit as st
import seaborn as sns
import matplotlib.pyplot as plt
from datetime import datetime
import zipfile
import io
import plotly.express as px
import pycountry

# Configuration
st.set_page_config(page_title="E-commerce Dashboard (1M Rows)", layout="wide")

st.title("📊 E-Commerce Analytics Dashboard")
st.markdown("""
**Developer:** Essam Afifi
**Contact:** esstoronto@gmail.com  
*Analyzing 1M+ transactions*
""")


# Cache data loading with 1-hour timeout
@st.cache_data(ttl=3600, show_spinner="Loading 1M records...")
def load_data():
    # Extract CSV from zip file
    with zipfile.ZipFile("ecommerce_data.zip") as z:
        # Get first CSV file in the zip (assuming only one exists)
        csv_filename = [f for f in z.namelist() if f.endswith('.csv')][0]
        with z.open(csv_filename) as f:
            dtype = {
                'InvoiceNo': 'str',
                'StockCode': 'str',
                'Quantity': 'float32',
                'UnitPrice': 'float32',
                'CustomerID': 'str',
                'TotalPrice': 'float32'
            }
            df = pd.read_csv(
                f,
                parse_dates=['InvoiceDate'],
                dtype=dtype
            )
    return df

# Function to convert country names to ISO Alpha-3 codes
@st.cache_data
def convert_to_iso(country_name):
    try:
        country = pycountry.countries.search_fuzzy(country_name)[0]
        return country.alpha_3
    except:
        return None

# Load data with progress bar
with st.spinner("Loading your 1 million records..."):
    try:
        df = load_data()
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        st.stop()

# Preprocessing (cached)
@st.cache_data
def preprocess(df):
    # Calculate month if not already in data
    if 'Month' not in df.columns:
        df['Month'] = df['InvoiceDate'].dt.to_period('M').astype(str)
    
    # Prepare country mapping for visualization
    if 'Country' in df.columns:
        unique_countries = df['Country'].unique()
        country_mapping = {country: convert_to_iso(country) for country in unique_countries}
        df['Country_ISO'] = df['Country'].map(country_mapping)
    
    return df

df = preprocess(df)

# SIDEBAR FILTERS
st.sidebar.header("🚦 Smart Filters")

# Year filter first to reduce data
df['Year'] = df['InvoiceDate'].dt.year
selected_year = st.sidebar.selectbox("Year", ["All"] + sorted(df['Year'].unique().tolist()))

# Dynamic country options based on year filter
country_options = ["All"] + sorted(
    df[df['Year'] == selected_year]['Country'].unique().tolist() 
    if selected_year != "All" 
    else df['Country'].unique().tolist()
)
selected_country = st.sidebar.selectbox("Country", country_options)

# Apply filters
filtered_df = df.copy()
if selected_year != "All":
    filtered_df = filtered_df[filtered_df['Year'] == selected_year]
if selected_country != "All":
    filtered_df = filtered_df[filtered_df['Country'] == selected_country]

# KPIs
col1, col2, col3, col4 = st.columns(4)
col1.metric("📊 Total Invoices", f"{filtered_df['InvoiceNo'].nunique():,}")
col2.metric("💰 Total Revenue", f"${filtered_df['TotalPrice'].sum():,.0f}")
col3.metric("🛒 Total Items", f"{filtered_df['Quantity'].sum():,}")
col4.metric("👥 Unique Customers", filtered_df['CustomerID'].nunique())

# MAIN DASHBOARD
st.header("📈 Performance Overview")

# Monthly trend chart
@st.cache_data
def plot_monthly_trend(data):
    fig, ax = plt.subplots(figsize=(10, 4))
    monthly_data = data.groupby('Month')['TotalPrice'].sum().reset_index()
    sns.lineplot(data=monthly_data, x='Month', y='TotalPrice', ax=ax)
    plt.xticks(rotation=45)
    ax.set_ylabel("Revenue ($)")
    return fig

st.pyplot(plot_monthly_trend(filtered_df))

# Top products
with st.expander("🔝 Top 10 Products by Revenue"):
    top_products = (
        filtered_df.groupby('Description')['TotalPrice']
        .sum()
        .nlargest(10)
        .reset_index()
    )
    st.dataframe(top_products)
    
    fig2, ax2 = plt.subplots(figsize=(8, 4))
    sns.barplot(data=top_products, y='Description', x='TotalPrice', ax=ax2, palette="Blues_d")
    ax2.set_xlabel("Revenue ($)")
    st.pyplot(fig2)

# Country analysis
with st.expander("🌍 Country Performance"):
    # Create tabs for table and map views
    tab1, tab2 = st.tabs(["📊 Data Table", "🗺️ Interactive Map"])
    
    with tab1:
        country_stats = (
            filtered_df.groupby('Country')
            .agg({'TotalPrice': 'sum', 'InvoiceNo': 'nunique'})
            .sort_values('TotalPrice', ascending=False)
            .rename(columns={'TotalPrice': 'Revenue', 'InvoiceNo': 'Invoices'})
        )
        st.dataframe(country_stats.style.format({'Revenue': '${:,.0f}'}))
    
    with tab2:

        st.info("💡 Map uses logarithmic scaling to better visualize revenue distribution across all markets. The UK dominates linear scales due to its size.")
        
        # Prepare data for the map
        map_data = (
            filtered_df.groupby(['Country', 'Country_ISO'])
            .agg({'TotalPrice': 'sum'})
            .reset_index()
            .rename(columns={'TotalPrice': 'Revenue'})
            .sort_values('Revenue', ascending=False)
        )
        
        # Remove rows with missing ISO codes
        map_data = map_data.dropna(subset=['Country_ISO'])
        
        # Add formatted revenue for hover text
        map_data['Revenue_Formatted'] = map_data['Revenue'].apply(lambda x: f"${x:,.0f}")

        # Create checkbox to exclude UK
        exclude_uk = st.checkbox("Exclude UK for better contrast on other countries", value=True)
        if exclude_uk:
            map_data = map_data[map_data['Country'] != 'United Kingdom']

        if not map_data.empty:
            # Create the choropleth map
            fig = px.choropleth(
                map_data,
                locations="Country_ISO",
                color="Revenue",
                hover_name="Country",
                hover_data={"Revenue_Formatted": True, "Country_ISO": False},
                color_continuous_scale=px.colors.sequential.Viridis,
                title="Revenue by Country (Log Scale)",
                projection="natural earth",
                range_color=[map_data['Revenue'].min(), map_data['Revenue'].max()],
                color_continuous_midpoint=map_data['Revenue'].quantile(0.75),
                labels={'Revenue_Formatted': 'Revenue'}
            )
            
            # Use logarithmic color scale
            fig.update_traces(
                zmin=1,  # Avoid log(0)
                zmax=map_data['Revenue'].max(),
                colorscale="Viridis",
                colorbar=dict(
                    title="Revenue (Log Scale)",
                    tickprefix="$",
                    ticks="outside",
                    tickvals=[10, 100, 1000, 10000, 100000, 1000000, 10000000],
                    ticktext=["10", "100", "1K", "10K", "100K", "1M", "10M"]
                )
            )

            # Adjust map layout
            fig.update_layout(
                margin={"r":0,"t":40,"l":0,"b":0},
                height=600,
                geo=dict(
                    showframe=False,
                    showcoastlines=True,
                    projection_type='natural earth'
                )

            )
            
            st.plotly_chart(fig, use_container_width=True)

            # Show data stats to help interpret
            st.caption(f"Revenue range: ${map_data['Revenue'].min():,.0f} - ${map_data['Revenue'].max():,.0f}")

        else:
            st.warning("No valid country data available for mapping.")

# Data sampling
with st.expander("📥 Download Options"):
    sample_size = st.slider("Sample rows to download", 1000, 10000, 5000)
    if st.button("Generate Sample CSV"):
        sample = filtered_df.sample(min(sample_size, len(filtered_df)))
        st.download_button(
            label="💾 Download Sample Data",
            data=sample.to_csv(index=False),
            file_name=f"ecommerce_sample_{datetime.now().date()}.csv",
            mime="text/csv"
        )