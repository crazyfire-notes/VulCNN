import argparse
import pickle
from functools import partial
from multiprocessing import Pool
from pathlib import Path

import networkx as nx
import numpy as np

import sent2vec

# Constants
NUM_PROCESSES = 10


def parse_options():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Image-based Vulnerability Detection.")
    parser.add_argument(
        "-i",
        "--input",
        help="The path of a dir which consists of some dot_files",
        required=True,
    )
    parser.add_argument("-o", "--out", help="The path of output.", required=True)
    parser.add_argument("-m", "--model", help="The path of model.", required=True)
    return parser.parse_args()


def graph_extraction(dot_file):
    """Extract graph from a dot file."""
    return nx.drawing.nx_pydot.read_dot(dot_file)


def sentence_embedding(sentence, model):
    """Embed a sentence using the provided model."""
    return model.embed_sentence(sentence)[0]


def extract_code_from_label(label):
    """Extract code from a node label."""
    code = label[label.index(",") + 1 : -2].split("\\n")[0]
    return code.replace("static void", "void")


def calculate_centralities(graph):
    """Calculate various centrality measures for the graph."""
    digraph = nx.DiGraph(graph)
    return {
        "degree": nx.degree_centrality(graph),
        "closeness": nx.closeness_centrality(graph),
        "katz": nx.katz_centrality(digraph),
    }


def generate_channels(graph, centralities, sent2vec_model):
    """Generate channels based on centralities and code embeddings."""
    labels_dict = nx.get_node_attributes(graph, "label")
    channels = {measure: [] for measure in centralities.keys()}

    for label, all_code in labels_dict.items():
        code = extract_code_from_label(all_code)
        line_vec = np.array(sentence_embedding(code, sent2vec_model))

        for measure, centrality_dict in centralities.items():
            centrality = centrality_dict[label]
            channels[measure].append(centrality * line_vec)

    return tuple(channels.values())


def image_generation(dot_file, sent2vec_model):
    """Generate image representation from a dot file."""
    try:
        graph = graph_extraction(dot_file)
        centralities = calculate_centralities(graph)
        return generate_channels(graph, centralities, sent2vec_model)
    except Exception as e:
        print(f"Error processing {dot_file}: {str(e)}")
        return None


def write_to_pkl(dot_file, out_dir, existing_files, sent2vec_model):
    """Process a single dot file and write the result to a pickle file."""
    dot_name = Path(dot_file).stem
    if dot_name in existing_files:
        return None

    print(f"Processing {dot_name}")
    channels = image_generation(dot_file, sent2vec_model)
    if channels is None:
        return None

    out_pkl = out_dir / f"{dot_name}.pkl"
    with open(out_pkl, "wb") as f:
        pickle.dump(channels, f)


def process_files(input_dir, out_dir, sent2vec_model):
    """Process all dot files in the input directory."""
    dot_files = list(Path(input_dir).glob("*.dot"))
    existing_files = {f.stem for f in out_dir.glob("*.pkl")}

    with Pool(NUM_PROCESSES) as pool:
        pool.map(
            partial(
                write_to_pkl,
                out_dir=out_dir,
                existing_files=existing_files,
                sent2vec_model=sent2vec_model,
            ),
            dot_files,
        )


def main():
    """Main function to orchestrate the vulnerability detection process."""
    args = parse_options()
    input_dir = Path(args.input)
    out_dir = Path(args.out)
    model_path = Path(args.model)

    # Ensure directories exist
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load the sent2vec model
    sent2vec_model = sent2vec.Sent2vecModel()
    sent2vec_model.load_model(str(model_path))

    try:
        process_files(input_dir, out_dir, sent2vec_model)
    finally:
        sent2vec_model.release_shared_mem(str(model_path))


if __name__ == "__main__":
    main()
