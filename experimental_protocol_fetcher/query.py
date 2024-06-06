from typing import List, Optional, Dict, Callable, Tuple
from kgforge.core import KnowledgeGraphForge
from getpass import getpass
import json

from experimental_protocol_fetcher.logger import logger
from helpers import _as_list, allocate


type_to_definition = {
    "NeuronMorphology": "Digital reconstruction of the geometry of a neuron. The reconstruction is always an approximation of the neuron and consists of a series of truncated cones or frusta.",
    "MEModel": "",
    "EModel": "",
    "Trace": "Electrophysiological recording of a neuron. It consists of a measurement of the neuron (normally voltage or current) over time."
}  # TODO query from ontology


# TODO how do we make sure all the data accessible through here (defaultSparqlView/ElasticSearchView) of OBP projects is actually available in the sbo es query view ?

def _resource_get(resource, field, type_):
    v = resource.__dict__.get(field, None)
    if v is None:
        raise Exception(f"Couldn't find {field} inside {type_} {resource.get_identifier()}")
    return v


def _locate_type(me_model_has_part, type_):
    res = next((i.get_identifier() for i in _as_list(me_model_has_part) if type_ in _as_list(i.get_type())), None)
    if res is None:
        raise Exception(f"Couldn't find {type_} in hasPart of MEModel")
    return res


def get_protocols_on_e_model(e_model_id: str, retrieve_or_raise: Callable, make_entry: Callable) -> Dict:

    e_model_resource = retrieve_or_raise(e_model_id, "EModel")
    e_model_generation = _resource_get(e_model_resource, "generation", "EModel")

    generation_with_followedWorkflow = next((i for i in _as_list(e_model_generation) if "activity" in i.__dict__ and "followedWorkflow" in i.activity.__dict__), None)

    if generation_with_followedWorkflow is None:
        raise Exception(f"Couldn't find generation/activity/followedWorkflow in EModel {e_model_id}")

    e_model_workflow_identifier = generation_with_followedWorkflow.activity.followedWorkflow.get_identifier()

    e_model_workflow_resource = retrieve_or_raise(e_model_workflow_identifier, "EModelWorkflow")

    e_model_workflow_hasPart = _resource_get(e_model_workflow_resource, "hasPart", "EModelWorkflow")

    extraction_targets_configuration_id = next(i.get_identifier() for i in _as_list(e_model_workflow_hasPart) if "ExtractionTargetsConfiguration" in _as_list(i.get_type()))
    e_model_configuration_id = next(i.get_identifier() for i in _as_list(e_model_workflow_hasPart) if "EModelConfiguration" in _as_list(i.get_type()))

    extraction_targets_configuration_resource = retrieve_or_raise(extraction_targets_configuration_id, "ExtractionTargetsConfiguration")

    e_model_configuration = retrieve_or_raise(e_model_configuration_id, "EModelConfiguration")

    extraction_targets_configuration_uses = _resource_get(extraction_targets_configuration_resource, "uses", "ExtractionTargetsConfiguration")
    e_model_uses = _resource_get(e_model_configuration, "uses", "EModelConfiguration")

    neuron_morphology_ids = [i.get_identifier() for i in e_model_uses if "NeuronMorphology" in _as_list(i.get_type())]

    if len(neuron_morphology_ids) != 1:
        raise Exception(f"Unexpected number of neuron morphologies inside the EModel: {len(neuron_morphology_ids)} instead of 1")

    traces_id = [i.get_identifier() for i in extraction_targets_configuration_uses]

    emodel_payload = make_entry(e_model_id, "EModel")
    emodel_payload["traces"] = [make_entry(trace_id, "Trace") for trace_id in traces_id]
    emodel_payload["morphology"] = make_entry(neuron_morphology_ids[0], "NeuronMorphology")

    return emodel_payload


def init(
        token: str,
        org="bbp",
        project="atlas",
        es_view="https://bbp.epfl.ch/neurosciencegraph/data/views/aggreg-es/sbo",
        sp_view="https://bbp.epfl.ch/neurosciencegraph/data/views/aggreg-sp/sbo",
        retrieve=True,
        is_prod=True
) -> Tuple[KnowledgeGraphForge, KnowledgeGraphForge, Callable, Callable]:

    forge_search = allocate(org, project, token=token, es_view=es_view, sp_view=sp_view, is_prod=is_prod)
    forge_protocols = allocate("bbp", "protocols", token=token, is_prod=is_prod) if retrieve else None

    def retrieve_or_raise(id_, type_):
        e = forge_search._store.retrieve(id_, cross_bucket=True, version=None)
        if e is None:
            raise Exception(f"Could not find {type_} {id_}")
        return e

    def make_entry(id_, type_):
        return {
            "about": {
                "type": type_,
                "type_definition": type_to_definition[type_],
            },
            "id": id_,
            **find_protocols(id_, parent=[], forge_search=forge_search, forge_protocols=forge_protocols, retrieve=retrieve)
        }

    return forge_search, forge_protocols, retrieve_or_raise, make_entry


def get_protocols_on_me_model(
        me_model_id: str, retrieve_or_raise: Callable, make_entry: Callable
) -> Dict:
    """
    For all emodels with workflow configurations: we can find the list of Traces by going into generation/activity/followedWorkflow and then within the Resource linked there
    (of type EModelWorkflow), look for the property hasPart and pick the entry of type ExtractionTargetsConfiguration,
    and then within this resource, Traces are listed in the uses property.
    """

    me_model_resource = retrieve_or_raise(me_model_id, "MEModel")
    me_model_has_part = _resource_get(me_model_resource, "hasPart", "MEModel")
    morphology_id = _locate_type(me_model_has_part, "NeuronMorphology")
    e_model_id = _locate_type(me_model_has_part, "EModel")

    emodel_payload = get_protocols_on_e_model(e_model_id, retrieve_or_raise, make_entry)

    payload = make_entry(me_model_id, "MEModel")
    payload["morphology"] = make_entry(morphology_id, "NeuronMorphology")
    payload["emodel"] = emodel_payload

    return payload


def find_protocols(id_: str, forge_search: KnowledgeGraphForge, parent: List, forge_protocols: KnowledgeGraphForge, retrieve: bool, raise_: bool = False) -> Dict:

    resource = forge_search.retrieve(id_, cross_bucket=True)

    if resource is None and raise_:
        raise Exception(f"Couldn't find referenced entity {id_}")

    all_protocols = {"found": resource is not None, "protocols": [], "derivations": {}}

    if resource is None:
        return all_protocols

    def protocol_info(protocol_id):
        protocol_resource = forge_protocols.retrieve(protocol_id)

        info = {
            "id": protocol_id,
            "found": protocol_resource is not None
        }

        if protocol_resource is not None:
            publication_reference = protocol_resource.__dict__.get("publication", None)
            publication = forge_protocols.retrieve(publication_reference.get_identifier()) if publication_reference else None
            publication_content_url = publication.distribution.contentUrl if publication else None  # TODO is this safe
            info["publication"] = publication_content_url
            info["additionalInformation"] = publication_reference.__dict__.get("extra", None)  # TODO - figure out field name

        return info

    try:
        protocols = next(i.activity.hadProtocol for i in _as_list(resource.generation) if "activity" in i.__dict__ and "hadProtocol" in i.activity.__dict__)
    except Exception:
        protocols = []

    protocol_ids = [i.get_identifier() for i in _as_list(protocols)] if protocols else []

    if len(protocol_ids) > 0:
        logger.info(f"Resource {id_} (path: {parent}) has protocols {protocol_ids}")

    all_protocols["protocols"] = [protocol_info(i) for i in protocol_ids] if retrieve else [{"id": i} for i in protocol_ids]

    try:
        derivations = [i.entity for i in _as_list(resource.derivation)]
    except Exception:
        derivations = []

    derivation_ids = [i.get_identifier() for i in _as_list(derivations)] if derivations else []

    if len(derivation_ids) > 0:
        logger.info(f"Resource {id_} (path: {parent}) has derivation {derivations}, look into its protocols")
        new_parent = parent + [id_]

        derivation_protocols = [
            {"id": i, **find_protocols(i, parent=new_parent, forge_search=forge_search, forge_protocols=forge_protocols, retrieve=retrieve)}
            for i in derivation_ids
        ]
    else:
        derivation_protocols = []

    all_protocols["derivations"] = derivation_protocols

    return all_protocols


def get_protocols(
        id_: str,
        token: str,
        org="bbp",
        project="atlas",
        es_view="https://bbp.epfl.ch/neurosciencegraph/data/views/aggreg-es/sbo",
        sp_view="https://bbp.epfl.ch/neurosciencegraph/data/views/aggreg-sp/sbo",
        retrieve=True,
        is_prod=True
):
    forge_search = allocate(org, project, is_prod=is_prod, token=token, es_view=es_view, sp_view=sp_view)
    forge_protocols = allocate("bbp", "protocols", is_prod=True, token=token) if retrieve else None

    return find_protocols(id_, parent=[], forge_search=forge_search, forge_protocols=forge_protocols, retrieve=retrieve)


if __name__ == "__main__":

    token = ""
    forge_search, forge_protocols, retrieve_or_raise, make_entry = init(token=token, is_prod=True, retrieve=True)
    me_model_id = "https://bbp.epfl.ch/data/bbp/mmb-point-neuron-framework-model/fc98f29b-a608-44d2-b9c4-8f4b6dbfee8d"
    res = get_protocols_on_me_model(me_model_id, retrieve_or_raise, make_entry)
    print(json.dumps(res, indent=4))

    # e_model_id = "https://bbp.epfl.ch/data/bbp/mmb-point-neuron-framework-model/642fbfec-3e40-4123-8596-650bd03daf7b"
    # res = get_protocols_on_e_model(e_model_id,  retrieve_or_raise, make_entry)
    # print(json.dumps(res, indent=4))

    # token = get_token(is_prod=True)
    # id_ = "https://bbp.epfl.ch/neurosciencegraph/data/neuronmorphologies/0993c0e9-e83a-4571-a4f0-7a1ee738d0b4"
    # res = get_protocols(id_, token, retrieve=True)
    # print(json.dumps(res, indent=4))
    # exit()

    # # on test data
    # token = get_token(is_prod=False)
    # id_ = "https://bbp.epfl.ch/thing_with_a_protocol_0"
    # res = get_protocols(
    #     id_, token, org="SarahTest",
    #     project="PublicThalamusTest2", retrieve=False,
    #     es_view="https://bluebrain.github.io/nexus/vocabulary/defaultElasticSearchIndex",
    #     sp_view="https://bluebrain.github.io/nexus/vocabulary/defaultSparqlIndex",
    #     is_prod=False
    # )
    # print(json.dumps(res, indent=4))
    # exit()

    # content_url = "https://bbp.epfl.ch/nexus/v1/files/bbp-external/seu/https%3A%2F%2Fbbp.epfl.ch%2Fneurosciencegraph%2Fdata%2Fc11338b1-f3ec-4ebd-b8fe-20d162fabc69"
    # token = getpass.getpass()
    #
    # get_file(content_url, token, metadata_only=False, write_path="./dest.swc")
    # get_file(content_url, token, metadata_only=True)
