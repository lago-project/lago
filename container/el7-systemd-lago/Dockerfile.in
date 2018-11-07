FROM @BASE@

ARG lago_version
ARG rpm_dir="/lago-rpms/"

WORKDIR /

LABEL "com.github.lago-project.lago.version"="$lago_version"

RUN mkdir "$rpm_dir"

COPY deploy.sh /
COPY *.rpm "$rpm_dir"
RUN ./deploy.sh "$rpm_dir" && rm -r "$rpm_dir" deploy.sh

WORKDIR /lago-envs
