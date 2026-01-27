#!/bin/sh
echo "Ejecutando sincronización de servicios..."
curl -i -X POST -H "X-SYNC-TOKEN: $SYNC_TOKEN" http://web:5000/admin/sync_servicios
echo ""