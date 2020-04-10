import argparse
from riemann.config.config_loader import initialize_config
import wandb
from riemann.graph_embedding_train_schedule import GraphEmbeddingTrainSchedule
from riemann.train import train
from riemann.model import get_model
from riemann.data.data_loader import get_training_data

parser = argparse.ArgumentParser(description='Tool to train graph embeddings \
                                 as detailed in "Retrofitting Manifolds to \
                                 Semantic Graphs"')
parser.add_argument('-u', '--config_updates', type=str, default="", help=\
                    "Extra configuration to inject into config dict")
parser.add_argument('-f', '--config_file', type=str, default=None, help=\
                    "File to load config from")

def run(args):
    # Initialize wandb dashboard
    # wandb.init(project="retrofitting-manifolds")

    # Initialize Config
    initialize_config(args.config_file, load_config=
                      (args.config_file is not None),
                      config_updates=args.config_updates)

    data = get_training_data()

    # Generate model
    model = get_model(data)
    
    # Train
    train_schedule = GraphEmbeddingTrainSchedule(model)
    train(train_schedule)
    

parser.set_defaults(func=run)

if __name__ == "__main__":
    #subparsers = parser.add_subparsers()
    #command_parser = subparsers.add_parser('command', help='' )
    #command_parser.set_defaults(func=do_command)
    ARGS = parser.parse_args()
    if ARGS.func is None:
        parser.print_help()
        sys.exit(1)
    else:
        ARGS.func(ARGS)