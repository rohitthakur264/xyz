import json
from rag.example_learner import ExampleLearner
from rag.vector_store import VectorStore
from config.settings import CHROMA_PERSIST_DIR

with open('../schema_intel/schema_cache.json') as f:
    schema_cache = json.load(f)

vs = VectorStore(persist_dir=CHROMA_PERSIST_DIR)
learner = ExampleLearner(vs, schema_cache)
learned = learner.learn()
print(f"Learned {learned} examples.")
