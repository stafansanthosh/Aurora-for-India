# Aurora India AQI Benchmark Spec

## Research question
Can Aurora, a global Earth-system foundation model, produce useful air-quality forecasts for Indian cities?

## First scope
Start with one city: Bangalore or Delhi.
Start with one pollutant: PM2.5.

## Ground truth
CPCB / CAAQMS station-level PM2.5 measurements.

## Model input
ERA5 / CAMS atmospheric gridded data.

## Evaluation
Compare Aurora predictions against CPCB station readings.

## Metrics
- MAE
- RMSE
- Correlation

## Baseline
Persistence baseline:
PM2.5 at t+1 = PM2.5 at t

## Success criteria for May
- Aurora inference runs
- One CPCB dataset loaded
- One ERA5/CAMS sample loaded
- First station-to-grid comparison completed
