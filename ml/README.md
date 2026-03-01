# ML Pipeline — DengueWatch SG

## Overview

Weekly XGBoost batch inference pipeline deployed on Amazon SageMaker.

## Directory Structure

```
ml/
├── scripts/
│   ├── train.py       # SageMaker training entry point
│   └── inference.py   # SageMaker batch inference entry point
├── notebooks/         # Exploratory data analysis (add Jupyter notebooks here)
└── requirements.txt
```

## Features

| Feature | Description |
|---|---|
| `lag_cases_1w` … `lag_cases_4w` | Dengue case counts for the past 1–4 weeks |
| `lag_rainfall_2w`, `lag_rainfall_3w` | Mean rainfall 2–3 weeks prior |
| `lag_temp_2w`, `lag_temp_3w` | Mean temperature 2–3 weeks prior |
| `week_sin`, `week_cos` | Sine/cosine encoding of `week_of_year` |

## Training

```bash
# Local test
python scripts/train.py \
    --train data/train.csv \
    --validation data/validation.csv \
    --model-dir model/

# SageMaker training job — triggered via CDK / boto3
```

## Inference

```bash
python scripts/inference.py \
    --model-dir model/ \
    --input-data s3://my-bucket/features/2024-W10.csv \
    --week 2024-W10
```

## Schedule

Amazon EventBridge rule fires every Monday at 06:00 SGT (UTC+8)
→ triggers a SageMaker Processing Job running `inference.py`.
