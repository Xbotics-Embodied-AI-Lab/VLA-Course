import unittest

from scripts.feishu_course_downloader import (
    build_cookie_header,
    build_download_url,
    collect_files,
    files_from_manifest_data,
    iter_ranges,
    sanitize_path_segment,
)


class FeishuCourseDownloaderTests(unittest.TestCase):
    def test_collect_files_filters_media_and_keeps_heading_hierarchy(self):
        payload = {
            "data": {
                "block_sequence": [
                    "part",
                    "chapter",
                    "lesson",
                    "keep_zip",
                    "skip_video",
                    "skip_pdf",
                    "skip_ppt",
                ],
                "block_map": {
                    "part": {
                        "data": {
                            "type": "heading1",
                            "text": {
                                "initialAttributedTexts": {
                                    "text": {"0": "第一部分：基础篇"}
                                }
                            },
                        }
                    },
                    "chapter": {
                        "data": {
                            "type": "heading2",
                            "text": {
                                "initialAttributedTexts": {
                                    "text": {"0": "第2章：具身智能基础工具与框架"}
                                }
                            },
                        }
                    },
                    "lesson": {
                        "data": {
                            "type": "heading3",
                            "text": {
                                "initialAttributedTexts": {
                                    "text": {"0": "2.1 PyTorch及PyTorchLightning框架"}
                                }
                            },
                        }
                    },
                    "keep_zip": {
                        "data": {
                            "type": "file",
                            "file": {
                                "name": "lesson_code.zip",
                                "mimeType": "application/zip",
                                "size": 123,
                                "token": "tok_zip",
                            },
                        }
                    },
                    "skip_video": {
                        "data": {
                            "type": "file",
                            "file": {
                                "name": "demo.mp4",
                                "mimeType": "video/mp4",
                                "size": 456,
                                "token": "tok_mp4",
                            },
                        }
                    },
                    "skip_pdf": {
                        "data": {
                            "type": "file",
                            "file": {
                                "name": "slides.pdf",
                                "mimeType": "application/pdf",
                                "size": 789,
                                "token": "tok_pdf",
                            },
                        }
                    },
                    "skip_ppt": {
                        "data": {
                            "type": "file",
                            "file": {
                                "name": "deck.pptx",
                                "mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                "size": 111,
                                "token": "tok_ppt",
                            },
                        }
                    },
                },
            }
        }

        files = collect_files([payload])

        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].name, "lesson_code.zip")
        self.assertEqual(
            files[0].relative_path,
            "第一部分：基础篇/第2章：具身智能基础工具与框架/2.1 PyTorch及PyTorchLightning框架/lesson_code.zip",
        )

    def test_collect_files_deduplicates_by_token_across_repeated_pages(self):
        def payload(heading: str):
            return {
                "data": {
                    "block_sequence": ["heading", "file"],
                    "block_map": {
                        "heading": {
                            "data": {
                                "type": "heading1",
                                "text": {
                                    "initialAttributedTexts": {
                                        "text": {"0": heading}
                                    }
                                },
                            }
                        },
                        "file": {
                            "data": {
                                "type": "file",
                                "file": {
                                    "name": "code.zip",
                                    "mimeType": "application/zip",
                                    "size": 123,
                                    "token": "same_token",
                                },
                            }
                        },
                    },
                }
            }

        files = collect_files([payload("第一处"), payload("重复片段")])

        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].relative_path, "第一处/code.zip")

    def test_collect_files_keeps_part_when_part_and_chapter_are_both_heading1(self):
        payload = {
            "data": {
                "block_sequence": ["part", "chapter", "lesson", "file"],
                "block_map": {
                    "part": {
                        "data": {
                            "type": "heading1",
                            "text": {
                                "initialAttributedTexts": {
                                    "text": {"0": "第一部分：基础篇"}
                                }
                            },
                        }
                    },
                    "chapter": {
                        "data": {
                            "type": "heading1",
                            "text": {
                                "initialAttributedTexts": {
                                    "text": {"0": "第2章：具身智能基础工具与框架"}
                                }
                            },
                        }
                    },
                    "lesson": {
                        "data": {
                            "type": "heading2",
                            "text": {
                                "initialAttributedTexts": {
                                    "text": {"0": "2.1 PyTorch及PyTorchLightning框架"}
                                }
                            },
                        }
                    },
                    "file": {
                        "data": {
                            "type": "file",
                            "file": {
                                "name": "code.zip",
                                "mimeType": "application/zip",
                                "size": 123,
                                "token": "tok",
                            },
                        }
                    },
                },
            }
        }

        files = collect_files([payload])

        self.assertEqual(
            files[0].relative_path,
            "第一部分：基础篇/第2章：具身智能基础工具与框架/2.1 PyTorch及PyTorchLightning框架/code.zip",
        )

    def test_collect_files_keeps_chapter_subpart_under_chapter(self):
        payload = {
            "data": {
                "block_sequence": ["part", "chapter", "subpart", "file"],
                "block_map": {
                    "part": {
                        "data": {
                            "type": "heading1",
                            "text": {
                                "initialAttributedTexts": {
                                    "text": {"0": "第四部分：VLA算法的后训练"}
                                }
                            },
                        }
                    },
                    "chapter": {
                        "data": {
                            "type": "heading1",
                            "text": {
                                "initialAttributedTexts": {
                                    "text": {"0": "第9章：科研臂VLA实践"}
                                }
                            },
                        }
                    },
                    "subpart": {
                        "data": {
                            "type": "heading2",
                            "text": {
                                "initialAttributedTexts": {
                                    "text": {"0": "第三部分：Diffusion 算法"}
                                }
                            },
                        }
                    },
                    "file": {
                        "data": {
                            "type": "file",
                            "file": {
                                "name": "dp.zip",
                                "mimeType": "application/zip",
                                "size": 123,
                                "token": "tok_dp",
                            },
                        }
                    },
                },
            }
        }

        files = collect_files([payload])

        self.assertEqual(
            files[0].relative_path,
            "第四部分：VLA算法的后训练/第9章：科研臂VLA实践/第三部分：Diffusion 算法/dp.zip",
        )

    def test_sanitize_path_segment_removes_unsafe_filesystem_characters(self):
        self.assertEqual(
            sanitize_path_segment("  a/b:c*?\"<>|  "),
            "a-b-c------",
        )

    def test_build_download_url_uses_stream_download_endpoint(self):
        self.assertEqual(
            build_download_url("abc123", "https://course.example.com"),
            "https://course.example.com/space/api/box/stream/download/all/abc123",
        )

    def test_build_cookie_header_keeps_feishu_cookies(self):
        state = {
            "cookies": [
                {"domain": ".feishu.cn", "name": "session", "value": "abc"},
                {"domain": "example.com", "name": "ignored", "value": "nope"},
                {"domain": "course.example.feishu.cn", "name": "_csrf_token", "value": "csrf"},
            ]
        }

        self.assertEqual(
            build_cookie_header(state),
            "session=abc; _csrf_token=csrf",
        )

    def test_files_from_manifest_data_restores_course_file_entries(self):
        files = files_from_manifest_data(
            [
                {
                    "name": "code.zip",
                    "token": "tok",
                    "size": 123,
                    "mime_type": "application/zip",
                    "headings": ["第一部分：基础篇"],
                    "relative_path": "第一部分：基础篇/code.zip",
                }
            ]
        )

        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].token, "tok")
        self.assertEqual(files[0].relative_path, "第一部分：基础篇/code.zip")

    def test_iter_ranges_chunks_from_resume_offset(self):
        self.assertEqual(
            list(iter_ranges(size=10, start=3, chunk_size=4)),
            [(3, 6), (7, 9)],
        )


if __name__ == "__main__":
    unittest.main()
