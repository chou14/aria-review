# services/r-analysis — plumber + bibliometrix 分析内核
FROM rocker/r-ver:4.3.3

# bibliometrix / plumber 的系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
      libcurl4-openssl-dev libssl-dev libxml2-dev libsodium-dev \
      libfontconfig1-dev libfreetype6-dev libuv1-dev libpoppler-cpp-dev \
      pkg-config pandoc curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY renv.lock renv.lock

# R 依赖版本由 renv.lock 锁定; renv 自身固定到生成 lockfile 的版本。
RUN R -q -e "install.packages('remotes', repos='https://cloud.r-project.org'); remotes::install_version('renv', version='1.2.3', repos='https://cloud.r-project.org'); renv::restore(project='.', library=.libPaths()[1], prompt=FALSE); stopifnot(requireNamespace('plumber', quietly=TRUE), requireNamespace('bibliometrix', quietly=TRUE), requireNamespace('jsonlite', quietly=TRUE), requireNamespace('httr2', quietly=TRUE), requireNamespace('digest', quietly=TRUE), requireNamespace('Matrix', quietly=TRUE))"

COPY R/ R/
COPY plumber.R entrypoint.R ./

ENV PORT=8001
ENV BIBLIOCN_CORPORA_DIR=/data/corpora
EXPOSE 8001
VOLUME ["/data/corpora"]

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -fsS "http://localhost:$PORT/healthz" || exit 1

CMD ["Rscript", "entrypoint.R"]
