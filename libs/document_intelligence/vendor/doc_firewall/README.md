# Vendored DocFirewall asset

`document_malware.yar` is DocFirewall's unmodified built-in ruleset from version
0.5.1. The published package omits this asset, and its binary-match formatter is
incompatible with the installed `yara-python` API. Newman Labs therefore runs the
same upstream rules as a raw-byte gate before DocFirewall. Remove this directory
and gate when a verified DocFirewall release handles both cases itself.

Source: <https://github.com/doc-firewall/doc-firewall/blob/v0.5.1/src/doc_firewall/rules/document_malware.yar>

Copyright (c) 2026 DocFirewall Contributors. Licensed under the MIT License;
the required license text is included beside the rules file.
