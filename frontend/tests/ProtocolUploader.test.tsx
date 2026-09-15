import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { ProtocolUploader } from '../src/components/ProtocolUploader';
import * as api from '../src/services/api';

vi.mock('../src/services/api', async () => {
  const actual = await vi.importActual('../src/services/api');
  return {
    ...actual,
    extractProtocol: vi.fn(),
    getTrials: vi.fn().mockResolvedValue([]),
    getHealthStatus: vi.fn().mockResolvedValue({ status: 'ok', service: 'fastapi' }),
  };
});

describe('ProtocolUploader error handling & timeout', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('exports PROTOCOL_EXTRACTION_TIMEOUT_MS configured to 120,000ms', () => {
    expect(api.PROTOCOL_EXTRACTION_TIMEOUT_MS).toBe(120000);
  });

  it('recovers from timeout error and resets loading states in finally', async () => {
    const timeoutError = new Error(
      'Protocol extraction request timed out after 120 seconds. The backend server may be waking up from cold-start or processing a complex protocol. Please try again.'
    );
    vi.mocked(api.extractProtocol).mockRejectedValueOnce(timeoutError);

    const { container } = render(<ProtocolUploader />);

    // Select a file
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;

    const file = new File(['%PDF-mock'], 'SYN_CARDIO_001.pdf', { type: 'application/pdf' });
    fireEvent.change(fileInput, { target: { files: [file] } });

    // Click upload
    const uploadBtn = screen.getByRole('button', { name: /extract protocol criteria/i });
    fireEvent.click(uploadBtn);

    // Wait for the error message to display and loading state to reset
    await waitFor(() => {
      expect(screen.getByText(/Protocol extraction request timed out after 120 seconds/i)).toBeDefined();
      const btn = screen.getByRole('button', { name: /extract protocol criteria/i }) as HTMLButtonElement;
      expect(btn.disabled).toBe(false);
      expect(screen.queryByText(/Extracting Criteria\.\.\./i)).toBeNull();
    });
  });

  it('recovers from CORS/network error and resets loading states in finally', async () => {
    const corsError = new Error(
      'Unable to reach backend server (Failed to fetch). Please check your network connection and verify backend status.'
    );
    vi.mocked(api.extractProtocol).mockRejectedValueOnce(corsError);

    const { container } = render(<ProtocolUploader />);

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['%PDF-mock'], 'SYN_CARDIO_001.pdf', { type: 'application/pdf' });
    fireEvent.change(fileInput, { target: { files: [file] } });

    const uploadBtn = screen.getByRole('button', { name: /extract protocol criteria/i });
    fireEvent.click(uploadBtn);

    await waitFor(() => {
      expect(screen.getByText(/Unable to reach backend server/i)).toBeDefined();
      const btn = screen.getByRole('button', { name: /extract protocol criteria/i }) as HTMLButtonElement;
      expect(btn.disabled).toBe(false);
      expect(screen.queryByText(/Extracting Criteria\.\.\./i)).toBeNull();
    });
  });
});
