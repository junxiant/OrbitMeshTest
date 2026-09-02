import '@testing-library/jest-dom';

// Stub scrollIntoView which is not implemented in jsdom
window.HTMLElement.prototype.scrollIntoView = function() {};
