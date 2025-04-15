### Pre-Release Checklist

Notes to keep track of the steps involved in making a new release.

- [ ] Check that the IP address in /aot-ai/scripts/generate_manual_api.sh is accessible and is the latest yet-to-be released version of AoT-AI.
- [ ] Ensure the virtualenv exists with ```sudo /opt/AoT-AI/aot-ai/scripts/upgrade_commands.sh setup-virtualenv-full```
- [ ] Update pip packages in virtualenv with ```/opt/AoT-AI/env/bin/pip install --break-system-packages -r /opt/AoT-AI/docs/requirements.txt```
- [ ] Install the dependencies listed at the top of generate_manual_api.sh
- [ ] Activate the virtualenv with ```source /opt/AoT-AI/env/bin/activate```
- [ ] Run ```sudo /bin/bash /opt/AoT-AI/aot-ai/scripts/generate_all.sh```
   - Generates Input/Output/Function/Widget/API manual pages in AoT-AI/docs/, and translatable .po files in AoT-AI/aot-ai/aot-ai_flask/translations, and translated docs.
- [ ] Verify the Input information was successfully inserted into the AoT-AI Manuals.
- [ ] Pull, translate words/phrases, and submit pull request, at https://translate.kylegabriel.com/projects/aot-ai/translations/ then merge into AoT-AI repo
    - Note: f-strings cannot be used with gettext() for translations, use format()
- [ ] Update config.py variables AOT-AI_VERSION and ALEMBIC_VERSION (if applicable).
- [ ] Update version in README.rst
- [ ] Update version in mkdocs.yml
- [ ] Update changes in CHANGELOG.md
   - Title in format "## 8.5.3 (2020-06-06)", with current date.
   - Section headers "### Bugfixes", "### Features", and "### Miscellaneous".
   - Changes as bullet list under each section header, with a link to issue(s) at the end of each short description (if applicable).
- [ ] Commit changes and wait for TravisCI to finish running pytests and verify all were successful.
- [ ] Install mkdocs dependencies:
   - ```sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libopenjp2-7```
   - ```/opt/AoT-AI/env/bin/python -m pip install --break-system-packages -r /opt/AoT-AI/docs/requirements.txt```
- [ ] Clone AoT-AI fresh to a new directory and ensure mkdocs pip requirements are installed by running: ```cd AoT-AI && sudo aot-ai/scripts/upgrade_commands.sh setup-virtualenv && sudo env/bin/python -m pip install --break-system-packages -r docs/requirements.txt```
- [ ] Run ```cd AoT-AI && env/bin/python -m mkdocs gh-deploy``` to generate and push docs to gh-pages branch (for https://kizniche.github.io/AoT-AI)
- [ ] Optionally, a naive AoT-AI system with code prior to the yet-to-be released version can be upgraded to master to test its ability to upgrade (useful if experimental database schema changes are being performed during the upgrade).
- [ ] Make GitHub Release
   - Tag version follows format "vMAJOR.MINOR.BUGFIX" (e.g. v8.0.3)
   - Release title is the same but without "v" (e.g. 8.0.3)
   - Description is copied from CHANGELOG.md
- [ ] Attempt an upgrade with a naive AoT-AI at a release prior to the new release.
