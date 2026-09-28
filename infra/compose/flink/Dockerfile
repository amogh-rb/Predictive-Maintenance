# The stock flink:1.19-scala_2.12-java11 image ships no connectors. This
# session's SQL jobs (stream/flink/sql/) need Kafka (source + alerts sink),
# JDBC (TimescaleDB sinks) with the Postgres driver, and the S3 filesystem
# plugin (Garage, for the telemetry_lake_sink). Jar coordinates verified
# against Maven Central for this exact base image's Flink/Scala version.
FROM flink:1.19-scala_2.12-java11

RUN set -eux; \
    cd /opt/flink/lib; \
    curl -fsSLO https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-kafka/3.2.0-1.19/flink-sql-connector-kafka-3.2.0-1.19.jar; \
    curl -fsSLO https://repo1.maven.org/maven2/org/apache/flink/flink-connector-jdbc/3.2.0-1.19/flink-connector-jdbc-3.2.0-1.19.jar; \
    curl -fsSLO https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.3/postgresql-42.7.3.jar; \
    mkdir -p /opt/flink/plugins/s3-fs-hadoop; \
    curl -fsSL -o /opt/flink/plugins/s3-fs-hadoop/flink-s3-fs-hadoop-1.19.1.jar \
        https://repo1.maven.org/maven2/org/apache/flink/flink-s3-fs-hadoop/1.19.1/flink-s3-fs-hadoop-1.19.1.jar
