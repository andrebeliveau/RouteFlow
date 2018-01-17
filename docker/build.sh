#!/bin/sh
docker build -trfserver rfserver
docker build -tbasefrr basefrr
docker build -tfrra frra
docker build -tfrrb frrb
docker build -tfrrc frrc
docker build -tfrrd frrd
