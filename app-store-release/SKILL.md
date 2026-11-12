---
name: app-store-release
description: Prepare, upload and submit an iOS app update for App Store review, including version and build bumps, Fastlane metadata, signing, build attachment, and review submission. Use for App Store or TestFlight release requests.
---

# App Store release

Read the repository's AGENTS.md/CLAUDE.md, Fastfile, Appfile, Deliverfile, and release scripts. Discover the project/workspace, scheme, bundle ID, team, signing configuration, metadata, and credentials from those sources. Preserve existing workspace changes; use the intended release source. A Git tag/CI trigger may build only committed code, while a local archive includes workspace changes.

## Prepare

- Read `MARKETING_VERSION` and `CURRENT_PROJECT_VERSION` for the app and any extensions. Query App Store Connect for live/editable versions and uploaded builds before choosing increments. Follow the repo's numbering convention; do not assume the local build number is the latest.
- Prefer the configured API key. Common env names are `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_KEY_PATH`; repositories may store them in gitignored `fastlane/.env.secret`. Load without printing secrets. Resolve the `.p8` path to an **absolute path** for xcodebuild. Never copy credentials into this skill or tracked files.
- With Bundler/Fastlane, `Spaceship::ConnectAPI::Token.create(key_id:, issuer_id:, filepath:)` authenticates; `App.find(bundle_id)` gets the app. For installed Fastlane 2.230, use `Build.all(app_id: app.id, ...)`, or `get_builds(filter: { app: app.id }, ...).to_models`. Inspect installed method signatures if they differ.
- Increment version/build consistently and run repo-required build and relevant tests. Preserve unrelated metadata.
- For each App Store release, set “What's New” in Fastlane's `fastlane/metadata/<locale>/release_notes.txt` (or the repo's configured equivalent). The default text is “Improvements and fixes.”, in each locale's own language; keep a locale's file if it already holds an equivalent generic line. Write specific notes only if the user asks for them or supplies them: then use 1–3 short, user-facing bullets based on changes since the last shipped release, with no invented improvements and no internal implementation details. Keep supported locale notes consistent and verify the uploaded version's “What's New” matches.

## Create version and push metadata

An API-backed Fastlane `upload_to_app_store`/`deliver` call with explicit `app_version`, `skip_binary_upload: true`, and `skip_screenshots: true` can create the editable version and upload text metadata. Inspect the existing editable version first: Fastlane may rename it. Do not overwrite a different pending release without resolving the conflict.

Keep `submit_for_review: false` in this call: the build is not uploaded yet. The default end state of this skill is `Waiting for Review` (see Verify and finish). Stop at the draft only if the user asks for an upload only, a draft, or a TestFlight-only build. Submission for review does not release the app; never release it to the public without an explicit request.

## Archive and upload

Use the repo's working release lane if available. Otherwise use Xcode CLI; an Xcode MCP is optional:

```bash
xcodebuild -project "$PROJECT" -scheme "$SCHEME" -configuration Release \
  -destination 'generic/platform=iOS' -archivePath "$ARCHIVE" \
  -allowProvisioningUpdates -authenticationKeyPath "$ASC_KEY_PATH" \
  -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID" archive

xcodebuild -exportArchive -archivePath "$ARCHIVE" \
  -exportOptionsPlist "$EXPORT_OPTIONS" -exportPath "$EXPORT_DIR" \
  -allowProvisioningUpdates -authenticationKeyPath "$ASC_KEY_PATH" \
  -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID"
```

Use `-workspace` instead of `-project` where appropriate. Keep artifacts/logs in an ignored build directory. With current Xcode, export options for direct upload are `method: app-store-connect`, `destination: upload`, `signingStyle: automatic`, the project `teamID`, `uploadSymbols: true`, and **`manageAppVersionAndBuildNumber: false`** to preserve the chosen numbers. Check `xcodebuild -help` for the installed version. Do not enable `testFlightInternalTestingOnly` for an App Store candidate.

Inspect the archive's bundle ID/version/build before upload. Automatic export may use cloud-managed signing; absence of a local Apple Distribution identity alone does not prove uploading is blocked. If API-key export fails with `Cloud signing permission error`, an already signed-in Xcode account may have the required access: retry the export with `-allowProvisioningUpdates` but omit all three `-authenticationKey*` flags. This worked with Xcode 26.6; the API key still handled metadata and build attachment. Diagnose actual signing errors; never revoke working certificates as a routine retry.

## Verify and finish

- Check upload logs, then query the exact version/build until Apple reports `VALID`. If it reports `FAILED`/`INVALID`, investigate instead of repeatedly uploading. After ambiguous transport failures, check for the existing upload before retrying or bumping again. If processing remains pending after a reasonable bounded wait, report that state accurately.
- For an App Store draft, attach the processed build with `AppStoreVersion#select_build(build_id:)` and read the relationship back. Do not mistake successful metadata upload for a binary upload or build attachment.
- Submit the version for review, unless the user asked to stop earlier. Use the repo's submit lane if one exists. Otherwise call `upload_to_app_store`/`deliver` with the exact `app_version` and `build_number`, `submit_for_review: true`, `skip_binary_upload: true`, `skip_metadata: true`, `skip_screenshots: true`, `force: true`, and `precheck_include_in_app_purchases: false` (precheck cannot read in-app purchases with an API key). `skip_metadata: true` stops this call from changing metadata, the release type, or phased release; do not pass `automatic_release`, `auto_release_date`, or `phased_release`. These option names are from Fastlane 2.241; inspect the installed version if they differ. If the build has no export-compliance answer (`ITSAppUsesNonExemptEncryption` in Info.plist), stop and ask; do not guess `submission_information`. Then read the version back until its state is `WAITING_FOR_REVIEW`. If precheck fails, another review submission is in progress, or the state does not change, report that state; do not cancel or reject an existing submission without a request.
- Tag the shipped code after Apple reports the build `VALID`. The archive includes workspace changes, so the last commit alone is not what shipped. When the archive starts, record the tree hash of the whole workspace, untracked files included, without touching the real index: `idx="$(mktemp)" && rm "$idx"; GIT_INDEX_FILE="$idx" git add -A && GIT_INDEX_FILE="$idx" git write-tree; rm -f "$idx"`. Before committing, compute the hash again; if it differs, the workspace changed after the archive: stop and report instead of tagging. List the untracked files that `git add -A` will add (`git status --short`); stop if one is a key, certificate, `.env` file or other secret. Commit every workspace change that went into the archive (`git add -A`, release message), then confirm that `git rev-parse 'HEAD^{tree}'` equals the recorded hash. Tag that local commit **before** any push, so a rebase during the push cannot put unshipped remote changes under the tag. Use the repo's existing tag convention, else `v<MARKETING_VERSION>-<CURRENT_PROJECT_VERSION>` (e.g. `v1.35-45`), as an annotated tag. Then push the branch (the user's `push` helper if it is on `PATH`, else `git push`) and push only that tag (`git push origin <tag>`). If the push rebased, the tag stays on the original release commit; report both commits. If the tag already exists, do not move or overwrite it; report it. If the upload failed or the build is not `VALID`, do not commit or tag.
- Report the App Store Connect link, version/build, processing and draft/review state, the release type (with an automatic release, approval publishes the app with no further step), validation results, the release commit and tag, and any outstanding action. Distinguish App Store upload, TestFlight distribution, review submission, public release, and Git push.
