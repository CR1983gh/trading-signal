# Universe lists for the PrimeTrading-style signal service.
# US: liquid growth/leaders. Excludes (per Alex's scan): China/HK, Biotech,
# Defensive, Real Estate, Energy, Financials.
US_UNIVERSE = [
    # Mega/large liquid tech & growth
    "AAPL","MSFT","NVDA","GOOGL","AMZN","META","AVGO","TSLA","AMD","CRM",
    "ORCL","ADBE","NOW","INTU","QCOM","TXN","MU","AMAT","LRCX","KLAC",
    "ASML","PANW","CRWD","ZS","FTNT","NET","DDOG","SNOW","MDB","PLTR",
    "APP","NFLX","BKNG","ABNB","UBER","DASH","SPOT",
    "ADSK","PAYX","ADP","INTC","MRVL","ON","ARM","ANET","VRT","COHR",
    "CIEN","DELL","HPQ","CSCO","IBM","ACN","BRZE","HUBS","TEAM","MNDY",
    "HOOD","COIN","RBLX","ROKU","DUOL","TTD","SE","BROS",
    "ALAB","CRDO","NBIS","IONQ","RGTI","QBTS",
    # Expansion 2026-09-27: Tradegate-verified liquid additions
    "ADI","MPWR","TER","SNPS","CDNS","MELI","SHOP","APLD","WDC","GEV","CRCL",
    "AXON","KTOS","LUNR","RDW",
    "NKE","LULU","SBUX","CMG","YUM","MCD",
    "DIS","CHTR","LYV",
    "TDG","HEI","HWM",
    "CAT","DE","PCAR","EMR","ETN","ROK","PH","ITW","MLM",
    "UNP","NSC","FDX","MATX","WAB",
]
US_TICKERS = list(dict.fromkeys(US_UNIVERSE))

# German: DAX 40 + liquid MDAX growth names (Yahoo tickers)
DE_UNIVERSE = [
    # DAX 40
    "SAP.DE","SIE.DE","AIR.DE","BMW.DE","MBG.DE","VOW3.DE","BAS.DE","BAYN.DE",
    "DTE.DE","IFX.DE","INS.DE","MUV2.DE","DPG.DE","RWE.DE","ALV.DE","1AT1.DE",
    "P911.DE","RHM.DE","MTX.DE","NEM.DE","ZAL.DE","SCA.DE","DD1.DE","CYR.DE",
    "AIXA.DE","DTG.DE","FME.DE","HEG.DE","HNR1.DE","KBX.DE","LEG.DE","NRK.DE",
    "PAP.DE","QIA.DE","R3N.DE","SRT.DE","ST1.DE","SY1.DE","TLG.DE",
    "UNA.DE","WCH.DE",
]
DE_TICKERS = list(dict.fromkeys(DE_UNIVERSE))

MARKET_REFERENCES = {
    "market": "QQQE",       # equal-weight US tech proxy (Alex's market health gauge)
    "bench_us": "SPY",
    "bench_de": "^GDAXI",
}
