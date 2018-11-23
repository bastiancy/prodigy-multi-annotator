FROM jupyter/scipy-notebook:1145fb1198b2

# Install from requirements.txt file
COPY ./*.whl /tmp/

RUN pip install 'spacy==2.0.12' 'psycopg2-binary==2.7.5' && \
	pip install /tmp/prodigy-1.5*.whl && \
	python -m spacy download en

RUN fix-permissions $CONDA_DIR && \
    fix-permissions /home/$NB_USER
