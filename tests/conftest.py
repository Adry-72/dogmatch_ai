import sys
import os
from unittest.mock import MagicMock
import numpy as np

# Aggiunge la root del progetto al path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Mocka sentence_transformers prima di qualsiasi import del progetto,
# così i test non caricano il modello da 471MB.
_mock_model = MagicMock()
_mock_model.encode.return_value = np.zeros((10, 384), dtype=np.float32)

_mock_st = MagicMock()
_mock_st.SentenceTransformer.return_value = _mock_model

sys.modules["sentence_transformers"] = _mock_st
