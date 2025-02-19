import asyncio
from sklearn.metrics import pairwise_distances
from sklearn.preprocessing import normalize
from face_sdk_3divi import FacerecService
from bitstring import BitArray
from io import BytesIO
import networkx as nx
import numpy as np
import base64
import json
import os
with open('dump.json', 'r') as f:
    data_list = json.load(f)

from core.utils import get_all_images_by_task_id
from api.dependencies import get_async_session

async def main():
    session = await get_async_session()
    images = await get_all_images_by_task_id(session, 9)
    for image in images:
        print(image.image_path)


if __name__ == '__main__':
    asyncio.run(main())
    exit(0)

face_sdk_3divi_dir = "/home/slonyara/3DiVi_FaceSDK/3_24_2"
default_dll_path = "/home/slonyara/3DiVi_FaceSDK/3_24_2/lib/libfacerec.so"
service = FacerecService.create_service(
    dll_path=default_dll_path,
    facerec_conf_dir="/home/slonyara/3DiVi_FaceSDK/3_24_2/conf/facerec", )


recognizer = service.create_recognizer("recognizer_latest_v1000.xml", True, False, False)

zero_point = 0.5

def load_template_from_base64(blob_str):
    try:
        blob_bytes = base64.b64decode(blob_str)
        binary_stream = BytesIO(blob_bytes)
        return recognizer.load_template(binary_stream)
    except Exception as e:
        raise

def cosine_from_embeddings(embeddings) -> np.ndarray:
    embeddings = normalize(embeddings - zero_point, axis=1) # Shift back zero point and normalize
    return np.inner(embeddings, embeddings)

def cosine_from_euclidean(embeddings, sq_euc) -> np.ndarray:
    """
    Get pairwise cosine distances from euclidean distances
    embedding: int4 matrix of shape (N, C)
    sq_euc: matrix of shape (N, N) of precalculated squared euclidean dists
    """
    dq_norms = np.linalg.norm(embeddings - zero_point, axis=1)
    n1 = dq_norms[:, np.newaxis]
    n2 = dq_norms[np.newaxis, :]
    return ((n1 ** 2) + (n2 ** 2) - sq_euc) / (2 * n1 * n2)

def intra_filtering_graph(embeddings, quality, threshold=0.8, distance_thr=0.8,
    dists=None):
    embeddings = np.array(embeddings)

    if dists is None:
        embeddings = normalize(embeddings)
        dists = np.inner(embeddings, embeddings)

    qaas = np.minimum.outer(quality, quality)
    if qaas[0][0] > 2:
        qaas /= 100
    conn = (qaas - dists) <= threshold

    N = conn.shape[0]
    not_equal_mask = ~np.eye(N, dtype=bool)
    mask = not_equal_mask & conn & (dists > distance_thr)
    i1_array, i2_array = np.where(mask)
    connections = [(i, j, {"weight": dists[i, j]}) for i, j in zip(i1_array, i2_array)]
    G = nx.Graph(connections)
    communities = nx.algorithms.community.label_propagation_communities(G)
    group_labels = [-1] * len(embeddings)
    for i, b in enumerate(communities):
        for bb in b:
            group_labels[bb] = i

    return np.array(group_labels)

templates = []
quality_scores_list = []

for item in data_list:
    item = item[0]
    if "template" in item:
        blob = None
        for key in item["template"]:
            if isinstance(item["template"][key], dict) and "blob" in item["template"][key]:
                blob = item["template"][key]["blob"]
                break

        if blob is None:
            continue

        idx_unpacking = np.arange(512)
        idx_unpacking[::2] += 1
        idx_unpacking[1::2] -= 1

        template = load_template_from_base64(blob)
        byte_io = BytesIO()
        template.save(byte_io)
        template_bin = byte_io.getvalue()[4:]
        template_bin = BitArray(template_bin)
        predict_tensor = [template_bin[i * 4:(i + 1) * 4].int for i in idx_unpacking]

        templates.append(predict_tensor)

    if "confidence" in item:
        print(item.keys())
        print(item)
        quality_scores_list.append(item["qaa"])

quality_scores_array = np.array(quality_scores_list)

templates = np.array(templates)
euc = pairwise_distances(templates, templates)
sq_euc = np.power(euc, 2)
cos_from_euc = cosine_from_euclidean(templates, sq_euc)
distances = cos_from_euc
labels = intra_filtering_graph(templates, quality_scores_array, dists=distances)
print(labels)

#[0 1 2 3 4 1 5 2 0 3 6 7 4 6 5 7]