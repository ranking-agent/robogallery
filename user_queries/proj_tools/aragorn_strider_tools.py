#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jul  9 14:43:21 2021

@author: priyash
"""

import json
import requests
#from datetime import datetime as dt
from collections import defaultdict
import pandas as pd


#https://pypi.org/project/gamma-viewer/
#from gamma_viewer import GammaViewer
#from IPython.display import display, Markdown


def printjson(j):
    print(json.dumps(j,indent=4))
def print_json(j):
    printjson(j)
    
def post(name,url,message,params=None):
    if params is None:
        response = requests.post(url,json=message)
    else:
        response = requests.post(url,json=message,params=params)
    if not response.status_code == 200:
        print(name, 'error:',response.status_code)
        print(response.json())
        return {}
    return response.json()

def automat(db,message):
    automat_url = f'https://automat.renci.org/{db}/1.1/query'
    response = requests.post(automat_url,json=message)
    print(response.status_code)
    return response.json()

def strider(message):
    #url = 'https://strider.renci.org/query?log_level=DEBUG' ## Old URL
    url = 'https://strider.renci.org/1.1/query' ## New URL
    #url = 'http://robokop.renci.org:5781/query'
    strider_answer = post(strider,url,message)
    return strider_answer

def aragorn(message, coalesce_type='xnone'):
    if coalesce_type == 'xnone':
        answer = post('aragorn','https://aragorn.renci.org/1.1/query',message)
    else:
        answer = post('aragorn','https://aragorn.renci.org/1.1/query',message, params={'answer_coalesce_type':coalesce_type})
    return answer

##

def bte(message):
    url = 'https://api.bte.ncats.io/v1/query'
    return post(strider,url,message)

def coalesce(message,method='all'):
    url = 'https://answercoalesce.renci.org/coalesce/graph'
    return post('AC'+method,url,message)

def striderandfriends(message):
    strider_answer = strider(message)    
    coalesced_answer = post('coalesce','https://answercoalesce.renci.org/coalesce/all',strider_answer)
    omni_answer = post('omnicorp','https://aragorn-ranker.renci.org/omnicorp_overlay',coalesced_answer)
    weighted_answer = post('weight','https://aragorn-ranker.renci.org/weight_correctness',omni_answer)
    scored_answer = post('score','https://aragorn-ranker.renci.org/score',weighted_answer)
    return strider_answer,coalesced_answer,omni_answer,weighted_answer,scored_answer

def print_errors(strider_result):
    errorcounts = defaultdict(int)
    for logmessage in strider_result['logs']:
        if logmessage['level'] == 'ERROR':
            jm = json.loads(logmessage['message'])
            words = jm['error'].split()
            e = " ".join(words[:-5])
            errorcounts[e] += 1
    for error,count in errorcounts.items():
        print(f'{error} ({count} times)')
        
def print_queried_sources(strider_result):
    querycounts = defaultdict(int)
    for logmessage in strider_result['logs']:
        if 'step' in logmessage and isinstance(logmessage['step'],list):
            for s in logmessage['step']:
                querycounts[s['url']] += 1
    for url,count in querycounts.items():
        print(f'{url} ({count} times)')
        
def print_query_for_source(strider_result,url):
    for logmessage in strider_result['logs']:
        if 'step' in logmessage and isinstance(logmessage['step'],list):
            for s in logmessage['step']:
                if s['url']==url:
                    print(s)
                    
                    
def retrieve_ars_results(mid):
    message_url = f'https://ars.transltr.io/ars/api/messages/{mid}?trace=y'
    response = requests.get(message_url)
    j = response.json()
    results = {}
    for child in j['children']:
        if child['actor']['agent'] in ['ara-aragorn', 'ara-aragorn-exp']:
            childmessage_id = child['message']
            child_url = f'https://ars.transltr.io/ars/api/messages/{childmessage_id}'
            child_response = requests.get(child_url).json()
            try:
                nresults = len(child_response['fields']['data']['message']['results'])
                if nresults > 0:
                    results[child['actor']['agent']] = {'message':child_response['fields']['data']['message']}
            except:
                nresults=0
            print( child['status'], child['actor']['agent'],nresults )
    return results


def get_provenance(message):
    """Given a message with results, find the source of the edges"""
    prov = defaultdict(lambda: defaultdict(int)) # {qedge->{source->count}}
    results = message['message']['results']
    kg = message['message']['knowledge_graph']['edges']
    edge_bindings = [ r['edge_bindings'] for r in results ]
    for bindings in edge_bindings:
        for qg_e, kg_l in bindings.items():
            for kg_e in kg_l:
                for att in kg[kg_e['id']]['attributes']:
                    if att['attribute_type_id'] == 'MetaInformation:Provenance':
                        source = att['value']
                        prov[qg_e][source]+=1
    qg_edges = []
    sources = []
    counts = []
    for qg_e in prov:
        for source in prov[qg_e]:
            qg_edges.append(qg_e)
            sources.append(source)
            counts.append(prov[qg_e][source])
    prov_table = pd.DataFrame({"QG Edge":qg_edges, "Source":sources, "Count":counts})
    return prov_table



def get_predicate(message):
    
    """Given a message with results, find the predicates """
    
    pred = defaultdict(lambda: defaultdict(int)) # {qedge->{source->count}}
    results = message['message']['results']
    kg = message['message']['knowledge_graph']['edges']
    edge_bindings = [ r['edge_bindings'] for r in results ]
    for bindings in edge_bindings:
        for qg_e, kg_l in bindings.items():
            for kg_e in kg_l:
                pred_id = kg[kg_e['id']]['predicate']
                pred[qg_e][pred_id]+=1
                
    qg_edges = []
    predicates = []
    counts = []
    for qg_e in pred:
        for preddies in pred[qg_e]:
            qg_edges.append(qg_e)
            predicates.append(preddies)
            counts.append(pred[qg_e][preddies])
    pred_table = pd.DataFrame({"QG Edge":qg_edges, "Predicate":predicates, "Count":counts})
    return pred_table


def which_nodes(message, predicate):
    
    """Given a message with results, and have extracted the unique predicates using get_predicate function """
    """Then find the nodes connected to the particular predicate of interest """
    
    node_id = []
    node_name = []
    node_source = []

    results = message['message']['results']
    kgn = message['message']['knowledge_graph']['nodes']
    kg = message['message']['knowledge_graph']['edges']
    edge_bindings = [ r['edge_bindings'] for r in results ]
    for bindings in edge_bindings:
        for qg_e, kg_l in bindings.items():
            for kg_e in kg_l:

                if kg[kg_e['id']]['predicate'] == predicate:
                    #print(kg[kg_e['id']])
                    idp = kg[kg_e['id']]['object']
                    name = kgn[idp]['name']
                    for att in kg[kg_e['id']]['attributes']:
                        source = att['value']

                    node_id.append(idp)
                    node_name.append(name)
                    node_source.append(source)


    node_table = pd.DataFrame({"Node ID":node_id, "Name":node_name, "Source":node_source,})
    return node_table

def make_message(qg):
    return {"message": {"query_graph": qg}}



if __name__ == "__main__":
    printjson()
    post()
    automat()
    strider()
    aragorn()
    bte()
    coalesce()
    striderandfriends()
    print_errors()
    print_errors()
    print_queried_sources()
    print_query_for_source()
    retrieve_ars_results()
    get_provenance()
    get_predicate() 
    which_nodes()
    make_message()
    
    
    
    
    
    