import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Timeline } from '../components/Timeline/Timeline';
import { TimelineHeader } from '../components/Timeline/TimelineHeader';
import { Scrubber } from '../components/Timeline/Scrubber';
import { TranscriptEditor } from '../components/TranscriptEditor/TranscriptEditor';
import { useMediaStore } from '../store/mediaStore';
import { useTimelineStore } from '../store/timelineStore';
import { useTranscriptStore } from '../store/transcriptStore';

const transcriptSegment = {
  id: 'segment-1',
  original_text: 'Hello world',
  translated_text: 'Hola mundo',
  start_time: 0,
  end_time: 2,
  speaker: 'Speaker 1',
  confidence: 0.9,
  words: [
    { text: 'Hello', start_time: 0, end_time: 0.8, confidence: 0.9 },
    { text: 'world', start_time: 1, end_time: 2, confidence: 0.9 },
  ],
  locked: false,
  edited: false,
};

describe('TranscriptEditor', () => {
  beforeEach(() => {
    useTranscriptStore.setState({ segments: [transcriptSegment], selectedSegmentId: null });
  });

  it('selects a segment, edits translation with confirmation, and exposes timing controls', async () => {
    const user = userEvent.setup();
    render(<TranscriptEditor />);

    await user.click(screen.getByText('Hello world'));
    expect(screen.getByRole('button', { name: 'Lock' })).toBeInTheDocument();
    expect(screen.getByText('Word-Level Timestamps')).toBeInTheDocument();

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Manual translation' } });
    expect(screen.getByText('Manual Override Confirmed')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Apply Override' }));
    expect(useTranscriptStore.getState().segments[0].translated_text)
      .toBe('Manual translation');
  });

  it('changes font size within bounds and operates on selected segments', async () => {
    const user = userEvent.setup();
    render(<TranscriptEditor />);
    await user.click(screen.getByText('Hello world'));

    for (let index = 0; index < 10; index += 1) {
      await user.click(screen.getByRole('button', { name: 'A+' }));
    }
    expect(screen.getByText('20px')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Lock' }));
    expect(useTranscriptStore.getState().segments[0].locked).toBe(true);
    expect(screen.getByRole('textbox')).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Unlock' }));
    await user.click(screen.getByRole('button', { name: 'Duplicate' }));
    expect(useTranscriptStore.getState().segments).toHaveLength(2);
  });

  it('splits and deletes selected segments', async () => {
    const user = userEvent.setup();
    render(<TranscriptEditor />);
    await user.click(screen.getByText('Hello world'));
    await user.click(screen.getByRole('button', { name: 'Split (Center)' }));
    expect(useTranscriptStore.getState().segments.map((segment) => segment.id))
      .toEqual(['segment-1_s1', 'segment-1_s2']);

    await user.click(screen.getByText('Hello'));
    await user.click(screen.getByRole('button', { name: 'Delete' }));
    expect(useTranscriptStore.getState().segments).toHaveLength(1);
  });

  it('cancels a pending manual override', async () => {
    const user = userEvent.setup();
    render(<TranscriptEditor />);
    await user.click(screen.getByText('Hello world'));
    await user.type(screen.getByRole('textbox'), ' changed');
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByText('Manual Override Confirmed')).not.toBeInTheDocument();
    expect(useTranscriptStore.getState().segments[0].translated_text).toBe('Hola mundo');
  });
});

describe('Timeline', () => {
  beforeEach(() => {
    useTimelineStore.setState({
      currentTimeSeconds: 0,
      isPlaying: false,
      zoomLevel: 100,
      selectedSegmentId: null,
    });
    useMediaStore.setState({
      metadata: null,
      isLoading: false,
      segments: [{
        id: 'segment-1',
        sequenceOrder: 1,
        startTimeSeconds: 1,
        endTimeSeconds: 3,
        durationSeconds: 2,
        speakerTag: 'Speaker 1',
        text: 'Hello',
        confidence: 0.9,
      }],
    });
  });

  it('renders controls and updates zoom, playback, and frame position', async () => {
    const user = userEvent.setup();
    const { container } = render(<Timeline audioData={null} durationSeconds={10} />);

    expect(screen.getByText('100%')).toBeInTheDocument();
    await user.click(screen.getByTitle('Zoom In'));
    expect(useTimelineStore.getState().zoomLevel).toBe(115);
    await user.click(screen.getByTitle('Zoom Out'));
    expect(useTimelineStore.getState().zoomLevel).toBe(100);
    await user.click(screen.getByTitle('Step Forward (Right Arrow)'));
    expect(useTimelineStore.getState().currentTimeSeconds).toBeCloseTo(0.04);

    const scrollPanel = container.querySelector('.overflow-x-auto') as HTMLDivElement;
    Object.defineProperty(scrollPanel, 'clientWidth', { configurable: true, value: 520 });
    await user.click(screen.getByTitle('Fit View to Window'));
    expect(useTimelineStore.getState().zoomLevel).toBe(50);
  });

  it('tracks horizontal scrolling', () => {
    const { container } = render(<Timeline audioData={null} durationSeconds={10} />);
    const scrollPanel = container.querySelector('.overflow-x-auto') as HTMLDivElement;
    fireEvent.scroll(scrollPanel, { target: { scrollLeft: 75 } });
    const ruler = container.querySelector('.h-8 > div') as HTMLDivElement;
    expect(ruler.style.transform).toBe('translateX(-75px)');
  });

  it('renders major and high-zoom minor timeline ticks', () => {
    const { container, rerender } = render(
      <TimelineHeader durationSeconds={1} zoomLevel={100} scrollLeft={10} />,
    );
    expect(container.querySelectorAll('.h-5')).toHaveLength(2);
    expect(container.querySelectorAll('.h-2\\.5')).toHaveLength(0);

    rerender(<TimelineHeader durationSeconds={1} zoomLevel={200} scrollLeft={0} />);
    expect(container.querySelectorAll('.h-2\\.5')).toHaveLength(9);
  });

  it('clamps scrubber clicks and drags to media duration', () => {
    const onScrub = vi.fn();
    const { container } = render(
      <Scrubber
        currentTimeSeconds={2}
        durationSeconds={10}
        zoomLevel={100}
        scrollLeft={20}
        onScrub={onScrub}
      />,
    );
    const scrubber = container.firstElementChild as HTMLDivElement;
    vi.spyOn(scrubber, 'getBoundingClientRect').mockReturnValue({
      left: 100,
      right: 1100,
      top: 0,
      bottom: 100,
      width: 1000,
      height: 100,
      x: 100,
      y: 0,
      toJSON: () => ({}),
    });

    fireEvent.mouseDown(scrubber, { clientX: 50 });
    expect(onScrub).toHaveBeenLastCalledWith(0);
    fireEvent.mouseMove(window, { clientX: 1500 });
    expect(onScrub).toHaveBeenLastCalledWith(10);
    fireEvent.mouseUp(window);
  });
});
