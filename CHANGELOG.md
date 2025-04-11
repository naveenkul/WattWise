# Changelog

## 0.1.4

### Fixed
- Fixed "event loop is closed" error when running `wattwise --watch` command
- Implemented persistent event loop in Kasa module to prevent asyncio errors during continuous monitoring
- Improved error handling for device connections and updates

### Changed
- Refactored code to use a shared event loop across the application
- Centralized version management across the codebase
- Updated kasa.py to be compatible with the latest python-kasa version

### Added
- Added more detailed error messages for connection failures
- Improved debug logging for troubleshooting
- wattwise --discover for discovering all the Kasa devices on your local networks
