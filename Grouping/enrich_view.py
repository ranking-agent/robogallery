import panel as pn
import os
import json
import pandas as pd
import param

from collections import defaultdict

pn.extension("tabulator")

# Create and populate the data chooser
files = os.listdir(".")
jsons = [f for f in files if f.endswith(".json")]
jsons.sort()
jsons = [""]+jsons


## This is going to be the parsed input file in a way that makes it easy to access the data and control the view
class Data(param.Parameterized):
    response = param.Dict({})
    results = param.DataFrame(pd.DataFrame({}))
    enrichments = param.DataFrame(pd.DataFrame({}))
    data_select = param.ObjectSelector(default="",objects=jsons)

    @param.depends()

    def __init__(self, **params):
        super().__init__(**params)
        files = os.listdir(".")
        jsons = [f for f in files if f.endswith(".json")]
        jsons.sort()
        self.jsons = [""] + jsons

    @param.depends("results")
    def result_table(self):
        self.rtable = pn.widgets.Tabulator(self.results, selectable=1, show_index=False, editors={"name": None, "score": None})
        return self.rtable

    @param.depends("enrichments")
    def enrich_table(self):
        self.etable = pn.widgets.Tabulator(self.enrichments, selectable=1, show_index=False, editors={"rule": None, "p_value": None, "enrichment": None})
        self.add_result_filter()
        self.add_enrich_filter()
        return self.etable

    def add_result_filter(self):
        self.rtable.add_filter(pn.bind(self.results_filter, selection=self.etable.param.selection))

    def results_filter(self, rtable, selection=[]):
        if len(selection) == 0:
            return rtable
        index = selection[0]
        enrichment = self.enrichments.iloc[index]["enrichment_names"]
        names = self.enrichment2results[enrichment]
        return rtable[rtable["name"].isin(names)]

    def add_enrich_filter(self):
        self.etable.add_filter(pn.bind(self.enrich_filter, selection=self.rtable.param.selection))

    def enrich_filter(self, etable, selection=[]):
        if len(selection) == 0:
            return etable
        index = selection[0]
        result = self.results.iloc[index]["name"]
        enrichment = self.result2enrichments[result]
        return etable[etable["enrichment_names"].isin(enrichment)]


    @param.depends('data_select', watch=True)
    def load_select(self):
        if self.data_select == "":
            return
        filename = self.data_select
        with open(filename, "r") as inf:
            self.response=json.load(inf)
        self.get_results()
        self.get_enrichments()
        self.get_result2enrichments()
        self.invert_matches()

    def get_results(self):
        if "message" not in self.response:
            return
        results = self.response["message"]["results"]
        names = []
        scores = []
        for result in results:
            identifier = result["node_bindings"]["sn"][0]["id"]
            names.append(self.response["message"]["knowledge_graph"]["nodes"][identifier]["name"])
            scores.append(result["analyses"][0]["score"])
        df = pd.DataFrame({"name": names, "score": scores})
        df.sort_values(by="score", ascending=False, inplace=True)
        self.results = df

    def get_enrichments(self):
        results = self.response["message"]["results"]
        all_enrichments = set()
        for result in results:
            enrichments = result["enrichments"]
            all_enrichments.update(enrichments)
        all_enrichments = list(all_enrichments)
        p_values = []
        rules = []
        types = []
        enrichment_names = []
        for enrichment in all_enrichments:
            ag = self.response["message"]["auxiliary_graphs"][enrichment]
            # Handling rules is a bit messy now because properties can return two rules in one enrichment.
            # That's going to change and make this clearer.
            new_rules = get_rule(ag["attributes"], self.response)
            if not isinstance(new_rules, list):
                rules.append(new_rules)
            for att in ag["attributes"]:
                if att["attribute_type_id"] == "biolink:p_value":
                    if isinstance(att["value"], list):
                        p_values.extend(att["value"])
                        rules.extend(new_rules)
                        n_new_rows = len(att["value"])
                    else:
                        p_values.append(att["value"])
                        n_new_rows = 1
                if att["attribute_type_id"] == "biolink:supporting_study_method_type":
                    etype = att["value"]
            for i in range(n_new_rows):
                types.append(etype)
                enrichment_names.append(enrichment)
        df = pd.DataFrame(
            {"rule": rules, "p_value": p_values, "enrichment": types, "enrichment_names": enrichment_names})
        df.sort_values(by="p_value", ascending=True, inplace=True)
        self.enrichments = df

    def get_result2enrichments(self):
        results = self.response["message"]["results"]
        result_to_enrichments = {}
        for result in results:
            identifier = result["node_bindings"]["sn"][0]["id"]
            name = self.response["message"]["knowledge_graph"]["nodes"][identifier]["name"]
            result_to_enrichments[name] = result["enrichments"]
        self.result2enrichments = result_to_enrichments

    def invert_matches(self):
        enrichments_to_results = defaultdict(list)
        for result, enrichments in self.result2enrichments.items():
            for enrichment in enrichments:
                enrichments_to_results[enrichment].append(result)
        self.enrichment2results = enrichments_to_results

data = Data()

def get_rule(attributes,data):
    newatts = {a["attribute_type_id"]: a["value"] for a in attributes}
    if newatts["biolink:supporting_study_method_type"] == "graph_enrichment":
        try:
            if "biolink:subject" in newatts:
                subject_id = newatts["biolink:subject"]
                subject_name = data["message"]["knowledge_graph"]["nodes"][subject_id]["name"]
                object_name = "result"
            else:
                object_id = newatts["biolink:object"]
                object_name = data["message"]["knowledge_graph"]["nodes"][object_id]["name"]
                subject_name = "result"
            # this is not very general...
            keys = ",".join(newatts.keys())
            if "qualifier" in keys:
                aspect_qualifier = newatts.get("biolink:object_aspect_qualifier","")
                direction_qualifier = newatts.get("biolink:object_direction_qualifier","")
                predicate = f"{direction_qualifier} {aspect_qualifier}"
            else:
                predicate = newatts["biolink:predicate"]
            rule = f"({subject_name})-[{predicate}]->({object_name})"
        except Exception as e:
            rule = f"{str(newatts)} {e}"
            #rule = str(newatts)
    else:
        rule = newatts["biolink:chemical_role:"]
    return rule

## FILTERING

#def results_filter(result_df, selection=[], enrich=enrichments):
#    if not selection:
#        return result_df
#    index = selection[0]
#    enrichment = enrich.loc[index]["enrichment_names"]
#    names = enrich2result[enrichment]
#    return result_df[result_df["name"].isin(names)]


## Layout

row = pn.Row(data.result_table, data.enrich_table)
col = pn.Column(data.param.data_select, row)

col.servable()