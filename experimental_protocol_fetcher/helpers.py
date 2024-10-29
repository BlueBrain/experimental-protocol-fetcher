# This file is part of experimental-protocol-fetcher.
# Copyright 2024 Blue Brain Project / EPFL
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from enum import Enum
from typing import Optional, Dict

import requests
from kgforge.core import KnowledgeGraphForge

PROD_CONFIG_URL = "https://raw.githubusercontent.com/BlueBrain/nexus-forge/master/examples/notebooks/use-cases/prod-forge-nexus.yml"


class Deployment(Enum):
    PRODUCTION = "https://bbp.epfl.ch/nexus/v1"
    STAGING = "https://staging.nise.bbp.epfl.ch/nexus/v1"


def allocate(org, project, is_prod, token, es_view=None, sp_view=None):

    endpoint = Deployment.STAGING.value if not is_prod else Deployment.PRODUCTION.value

    bucket = f"{org}/{project}"

    args = dict(
        configuration=PROD_CONFIG_URL,
        bucket=bucket,
        token=token,
        endpoint=endpoint
    )

    search_endpoints = {}

    if es_view is not None:
        search_endpoints["elastic"] = {"endpoint": es_view}

    if sp_view is not None:
        search_endpoints["sparql"] = {"endpoint": sp_view}

    if len(search_endpoints) > 0:
        args["searchendpoints"] = search_endpoints

    return KnowledgeGraphForge(**args)


def get_file(content_url: str, token: str, metadata_only: bool, write_path: Optional[str] = None) -> Optional[Dict]:

    if not metadata_only and write_path is None:
        raise Exception("write_path needs to be set if metadata_only is False")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/ld+json" if metadata_only else "*/*"
    }

    response = requests.get(content_url, headers=headers, timeout=300)

    if not metadata_only:
        with open(write_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=4096):
                f.write(chunk)
        return None  # TODO return something here?

    else:
        metadata = response.json()
        return metadata


def _as_list(obj):
    return obj if isinstance(obj, list) else ([obj] if obj is not None else [])
