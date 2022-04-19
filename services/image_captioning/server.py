import logging
import time
import os
 
from transformers import BertTokenizer, BertForMaskedLM
import torch
from flask import Flask, request, jsonify
from healthcheck import HealthCheck
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
import clip
import os
import torch
from transformers import GPT2Tokenizer
import skimage.io as io
import PIL.Image
from model import ClipCaptionModel, generate_beam, generate2
 
sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"), integrations=[FlaskIntegration()])
 
 
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
 
D = torch.device
CPU = torch.device('cpu')
 
 
def get_device(device_id: int) -> D:
   if not torch.cuda.is_available():
       return CPU
   device_id = min(torch.cuda.device_count() - 1, device_id)
   return torch.device(f'cuda:{device_id}')
 
 
CUDA = get_device
 
PRETRAINED_MODEL_PATH = os.environ.get("PRETRAINED_MODEL_PATH")
current_directory = os.getcwd()
save_path = os.path.join(current_directory, "pretrained_models")
model_path = os.path.join(save_path, 'model_weights.pt')
 
try:
   device = CUDA(0)
 
   clip_model, preprocess = clip.load("ViT-B/32", device=device, jit=False)
   tokenizer = GPT2Tokenizer.from_pretrained("gpt2")
 
   prefix_length = 10
 
   model = ClipCaptionModel(prefix_length)
 
   model.load_state_dict(torch.load(PRETRAINED_MODEL_PATH, map_location=CPU))
 
   model = model.eval()
   model = model.to(device)
 
   logger.info("image captioning model is ready")
except Exception as e:
   sentry_sdk.capture_exception(e)
   logger.exception(e)
   raise e
 
app = Flask(__name__)
health = HealthCheck(app, "/healthcheck")
logging.getLogger("werkzeug").setLevel("WARNING")
 
 
@app.route("/respond", methods=["POST"])
def respond():
   st_time = time.time()
 
   image_path = request.json.get("text", [])
   try:
       image = io.imread(image_path)
       pil_image = PIL.Image.fromarray(image)
       image = preprocess(pil_image).unsqueeze(0).to(device)
       with torch.no_grad():
           prefix = clip_model.encode_image(image).to(device, dtype=torch.float32)
           prefix_embed = model.clip_project(prefix).reshape(1, prefix_length, -1)
       use_beam_search = False
       if use_beam_search:
           generated_text_prefix = generate_beam(model, tokenizer, embed=prefix_embed)[0]
       else:
           generated_text_prefix = generate2(model, tokenizer, embed=prefix_embed)
       return generated_text_prefix
   except Exception as exc:
       logger.exception(exc)
       sentry_sdk.capture_exception(exc)
       generated_text_prefix = ""
 
   total_time = time.time() - st_time
   logger.info(f"masked_lm exec time: {total_time:.3f}s")
   return jsonify({"caption": generated_text_prefix})
