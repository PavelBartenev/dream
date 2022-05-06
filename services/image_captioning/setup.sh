apt update
apt install git -y
pip install git+https://github.com/openai/CLIP.git
pip install gdown
# create dirs for data and models
mkdir -p /opt/conda/lib/python3.7/site-packages/data/models
gdown 1IdaBtMSvtyzF0ByVaBHtvM0JYSXRExRX -O /opt/conda/lib/python3.7/site-packages/data/models/coco_weights.pt