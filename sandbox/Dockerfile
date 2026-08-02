FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32

COPY runner.mjs /opt/junoguard/runner.mjs

USER 65534:65534
WORKDIR /work
ENTRYPOINT ["node", "/opt/junoguard/runner.mjs"]
