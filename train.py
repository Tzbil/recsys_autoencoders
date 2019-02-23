import click
import pandas as pd
import math
import numpy as np
import json
import mlflow
import mlflow.keras
from util import *
from contextlib import redirect_stdout

from keras.optimizers import Adam, RMSprop
from keras.layers import Input, Dense, Embedding, Flatten, Dropout, merge, Activation
from keras.models import Model
from keras.regularizers import l2
from keras import backend as K
from keras import regularizers
from keras.callbacks import ModelCheckpoint, EarlyStopping
from keras import initializers

from evaluation.model_evaluator import *
from model.CDAEModel import *
from model.AutoEncModel import *

# Const
TRAIN_HIST_PATH     = './artefacts/train_hist.png'
TRAIN_HIST_LOG_PATH = './artefacts/train_hist.json'
MODEL_SUMMARY_PATH  = './artefacts/model_summary.txt'
METRICS_LOG_PATH    = './artefacts/metrics.png'
SCORE_VALUES_PATH   = './artefacts/score_plot.png'

# ----------------------------------------------
# main
# ----------------------------------------------
@click.command(help="Autoencoder Matrix Fatorization Model")
@click.option("--model", type=click.Choice(['auto_enc', 'cdae']))
@click.option("--factors", type=click.INT, default=10)
@click.option("--layers", type=click.STRING, default='[128,256,128]')
@click.option("--epochs", type=click.INT, default=10)
@click.option("--batch", type=click.INT, default=64)
@click.option("--activation", type=click.Choice(['relu', 'elu', 'selu', 'sigmoid']))
@click.option("--dropout", type=click.FLOAT, default=0.6)
@click.option("--lr", type=click.FLOAT, default=0.001)
@click.option("--reg", type=click.FLOAT, default=0.001)
def run(model, factors, layers, epochs, batch, activation, dropout, lr, reg):
  
  # Load Dataset
  articles_df, interactions_full_df, \
    interactions_train_df, interactions_test_df, \
      cf_preds_df = load_dataset()

  print('# interactions on Train set: %d' % len(interactions_train_df))
  print('# interactions on Test set: %d' % len(interactions_test_df))

  #Creating a sparse pivot table with users in rows and items in columns
  users_items_matrix_df = interactions_train_df.pivot(index   = 'user_id', 
                                                      columns = 'content_id', 
                                                      values  = 'view').fillna(0)
  # Data
  users_items_matrix    = users_items_matrix_df.as_matrix()
  users_ids             = list(users_items_matrix_df.index)

  if model == 'cdae':
    # Input  
    x_user_ids = np.array(users_ids).reshape(len(users_ids), 1)
    X = [users_items_matrix, x_user_ids]
    y = users_items_matrix
    
    # Model
    model = CDAEModel(factors, epochs, batch, activation, dropout, lr, reg)

  elif model == 'auto_enc':

    # Input  
    X, y = users_items_matrix, users_items_matrix
    
    # Model
    model = AutoEncModel(layers, epochs, batch, activation, dropout, lr, reg)

  # ---------------------------------------------

  # Train
  k_model, hist  = model.fit(X, y)

  # Predict
  pred_score     = model.predict(X)

  # converting the reconstructed matrix back to a Pandas dataframe
  cf_preds_df = pd.DataFrame(pred_score, 
                              columns = users_items_matrix_df.columns, 
                              index=users_ids).transpose()
  
  # Plot Preds Scores
  plot_scores_values(cf_preds_df.sample(frac=0.1).values.reshape(-1), SCORE_VALUES_PATH)

  print("Sample Scores")
  print(cf_preds_df.iloc[0].values[:10])
  print(cf_preds_df.iloc[1].values[:10])

  # Evaluation Model
  cf_recommender_model = CFRecommender(cf_preds_df, articles_df)
  model_evaluator      = ModelEvaluator(articles_df, interactions_full_df, 
                                        interactions_train_df, interactions_test_df)    

  # Plot Summary model
  print_model_summary(k_model)

  # Plot History train model
  print_hist_log(hist)

  # Plot Evaluation
  print('Evaluating Collaborative Filtering model...')
  metrics, detailed_metrics = model_evaluator.evaluate_model(cf_recommender_model)
  print('\nGlobal metrics:\n%s' % metrics)

  # Plot Metrics
  plot_metrics_disc(metrics, METRICS_LOG_PATH)

  # Tracking
  with mlflow.start_run():
    # metrics
    for metric in ModelEvaluator.METRICS:
      mlflow.log_metric(metric, metrics[metric])
    
    # artefact
    mlflow.log_artifact(TRAIN_HIST_PATH, "history")
    mlflow.log_artifact(TRAIN_HIST_LOG_PATH, "history")
    mlflow.log_artifact(MODEL_SUMMARY_PATH)
    mlflow.log_artifact(METRICS_LOG_PATH, "evaluation")
    mlflow.log_artifact(SCORE_VALUES_PATH, "evaluation")

    #model
    mlflow.keras.log_model(k_model, "model")

def print_model_summary(model):
  # Save model summary
  print(model.summary())
  with open(MODEL_SUMMARY_PATH, 'w') as f:
    with redirect_stdout(f):
        model.summary()

def print_hist_log(hist):
  # save hist
  with open(TRAIN_HIST_LOG_PATH, 'w') as f:
    json.dump(hist.history, f)

  # save image hist
  plot_hist(hist).savefig(TRAIN_HIST_PATH)


if __name__ == '__main__':
    run()  