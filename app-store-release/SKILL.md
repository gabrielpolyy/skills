---
name: app-store-release
description: Prepare and upload an iOS app update to App Store Connect, including version and build bumps, Fastlane metadata, signing, and build attachment. Use for App Store or TestFlight release requests.
---

# App Store release

Read the repository's AGENTS.md/CLAUDE.md, Fastfile, Appfile, Deliverfile, and release scripts. Discover the project/workspace, scheme, bundle ID, team, signing configuration, metadata, and credentials from those sources. Preserve existing workspace changes; use the intended release source. A Git tag/CI trigger may build only committed code, while a local archive includes workspace changes.

## Prepare

- Read `MARKETING_VERSION` and `CURRENT_PROJECT_VERSION` for the app and any extensions. Query App Store Connect for live/editable versions and uploaded builds before choosing increments. Follow the repo's numbering convention; do not assume the local build number is the latest.
- Prefer the configured API key. Common env names are `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_KEY_PATH`; repositories may store them in gitignored `fastlane/.env.secret`. Load without printing secrets. Resolve the `.p8` path to an **absolute path** for xcodebuild. Never copy credentials into this skill or tracked files.
- With Bundler/Fastlane, `Spaceship::ConnectAPI::Token.create(key_id:, issuer_id:, filepath:)` authenticates; `App.find(bundle_id)` gets the app. For installed Fastlane 2.230, use `Build.all(app_id: app.id, ...)`, or `get_builds(filter: { app: app.id }, ...).to_models`. Inspect installed method signatures if they differ.
- Increment version/build consistently, run repo-required build and relevant tests, and inspect release notes. Use the repo's existing metadata unless the task calls for rewriting it.

## Create version and push metadata

An API-backed Fastlane `upload_to_app_store`/`deliver` call with explicit `app_version`, `skip_binary_upload: true`, and `skip_screenshots: true` can create the editable version and upload text metadata. Inspect the existing editable version first: Fastlane may rename it. Do not overwrite a different pending release without resolving the conflict.

Use `submit_for_review: false` for preparation/upload requests. Creating a draft and uploading a build do not submit or publish the app. Follow authorization already provided in the conversation; require additional direction only for actions outside that scope.

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

Inspect the archive's bundle ID/version/build before upload. Automatic export may use cloud-managed signing; absence of a local Apple Distribution identity alone does not prove uploading is blocked. If signing fails, diagnose the actual error; never revoke working certificates as a routine retry.

## Verify and finish

- Check upload logs, then query the exact version/build until Apple reports `VALID`. If it reports `FAILED`/`INVALID`, investigate instead of repeatedly uploading. After ambiguous transport failures, check for the existing upload before retrying or bumping again. If processing remains pending after a reasonable bounded wait, report that state accurately.
- For an App Store draft, attach the processed build with `AppStoreVersion#select_build(build_id:)` and read the relationship back. Do not mistake successful metadata upload for a binary upload or build attachment.
- Report the App Store Connect link, version/build, processing and draft/review state, validation results, and any outstanding action. Distinguish App Store upload, TestFlight distribution, review submission, public release, and Git push.
